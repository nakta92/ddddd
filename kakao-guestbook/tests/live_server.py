"""테스트 전용 실서버 런처: 카카오 OAuth를 가짜로 바꿔 uvicorn을 띄웁니다.

SSE처럼 응답이 끝나지 않는 기능이나 브라우저 동작은 TestClient로 검증하기 어려워 실제 서버로 확인합니다.
사용법: python -m tests.live_server <port>
  1) GET /__fake_kakao/as/{kakao_id}/{nickname}  -> 다음 로그인할 가짜 카카오 사용자 지정
  2) GET /auth/kakao/login                         -> 가짜 인가 페이지를 거쳐 콜백으로 로그인 완료
절대 운영 환경에서 실행하지 마세요.
"""

import sys
from urllib.parse import urlencode

import uvicorn
from fastapi.responses import RedirectResponse

from app import kakao
from app.main import app

_next_identity: dict = {"id": 1, "nickname": "테스터"}
_profiles: dict[str, kakao.KakaoProfile] = {}


def _fake_authorize_url(state: str) -> str:
    return "/__fake_kakao/authorize?" + urlencode({"state": state})


def _fake_exchange_token(code: str) -> str:
    return f"token:{code}"


def _fake_fetch_user(token: str) -> kakao.KakaoProfile:
    return _profiles[token.split(":", 1)[1]]


@app.get("/__fake_kakao/as/{kakao_id}/{nickname}", include_in_schema=False)
def fake_as(kakao_id: int, nickname: str):
    _next_identity.update(id=kakao_id, nickname=nickname)
    return {"ok": True, **_next_identity}


@app.get("/__fake_kakao/authorize", include_in_schema=False)
def fake_authorize(state: str):
    code = f"fake-{_next_identity['id']}"
    _profiles[code] = kakao.KakaoProfile(id=_next_identity["id"], nickname=_next_identity["nickname"], profile_image=None)
    return RedirectResponse("/auth/kakao/callback?" + urlencode({"code": code, "state": state}), status_code=302)


kakao.authorize_url = _fake_authorize_url
kakao.exchange_token = _fake_exchange_token
kakao.fetch_user = _fake_fetch_user


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
