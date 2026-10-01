"""카카오 REST API OAuth 2.0 클라이언트.

흐름: 인가 코드 요청(authorize) -> 콜백으로 code 수신 -> 토큰 발급(token) -> 사용자 정보 조회(user/me)
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from .config import settings

AUTH_BASE = "https://kauth.kakao.com"
API_BASE = "https://kapi.kakao.com"
TIMEOUT = httpx.Timeout(10.0)


class KakaoError(Exception):
    pass


@dataclass
class KakaoProfile:
    id: int
    nickname: str
    profile_image: str | None


def authorize_url(state: str) -> str:
    query = urlencode(
        {
            "client_id": settings.kakao_rest_api_key,
            "redirect_uri": settings.kakao_redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )
    return f"{AUTH_BASE}/oauth/authorize?{query}"


def exchange_token(code: str) -> str:
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.kakao_rest_api_key,
        "redirect_uri": settings.kakao_redirect_uri,
        "code": code,
    }
    if settings.kakao_client_secret:
        data["client_secret"] = settings.kakao_client_secret
    try:
        res = httpx.post(f"{AUTH_BASE}/oauth/token", data=data, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise KakaoError(f"카카오 토큰 요청 실패: {e}") from e
    body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
    if res.status_code != 200 or "access_token" not in body:
        raise KakaoError(f"카카오 토큰 발급 실패: {body.get('error_description') or res.status_code}")
    return body["access_token"]


def fetch_user(access_token: str) -> KakaoProfile:
    try:
        res = httpx.get(
            f"{API_BASE}/v2/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=TIMEOUT,
        )
    except httpx.HTTPError as e:
        raise KakaoError(f"카카오 사용자 정보 요청 실패: {e}") from e
    if res.status_code != 200:
        raise KakaoError(f"카카오 사용자 정보 조회 실패: {res.status_code}")
    body = res.json()
    account = body.get("kakao_account") or {}
    profile = account.get("profile") or {}
    props = body.get("properties") or {}
    return KakaoProfile(
        id=int(body["id"]),
        nickname=profile.get("nickname") or props.get("nickname") or f"카카오{body['id']}",
        profile_image=profile.get("profile_image_url") or props.get("profile_image"),
    )
