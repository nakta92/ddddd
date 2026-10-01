"""스모크 테스트 공통 설정.

- 임시 SQLite DB를 쓰고, 테스트마다 테이블을 새로 만듭니다.
- 카카오 API(토큰 발급/사용자 조회)는 가짜 함수로 바꿔 실제 네트워크 없이 OAuth 콜백 흐름을 검증합니다.
"""

import os
import tempfile
from urllib.parse import parse_qs, urlparse

_TMP = tempfile.mkdtemp(prefix="guestbook-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["KAKAO_REST_API_KEY"] = "test-rest-key"
os.environ["UPLOAD_DIR"] = f"{_TMP}/uploads"
os.environ["MAX_UPLOAD_MB"] = "1"  # 테스트에서는 1MB로 낮춰 크기 제한 검증

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import kakao  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import auth as auth_router  # noqa: E402

AJAX = {"X-Requested-With": "fetch"}
FAKE_PROFILES: dict[str, kakao.KakaoProfile] = {}


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    auth_router.reset_admin_throttle()
    monkeypatch.setattr(kakao, "exchange_token", lambda code: f"token:{code}")
    monkeypatch.setattr(kakao, "fetch_user", lambda token: FAKE_PROFILES[token.split(":", 1)[1]])
    yield


def kakao_login(client: TestClient, kakao_id: int, nickname: str, image: str | None = None, next_path: str = "/"):
    """가짜 카카오 프로필로 /auth/kakao/login -> /auth/kakao/callback 전체 흐름을 수행합니다."""
    code = f"code-{kakao_id}"
    FAKE_PROFILES[code] = kakao.KakaoProfile(id=kakao_id, nickname=nickname, profile_image=image)
    r = client.get("/auth/kakao/login", params={"next": next_path}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://kauth.kakao.com/oauth/authorize")
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    r = client.get("/auth/kakao/callback", params={"code": code, "state": state}, follow_redirects=False)
    assert r.status_code == 303
    return r


@pytest.fixture
def make_client():
    """사용자별로 쿠키가 분리된 클라이언트를 만듭니다. kakao_id를 주면 로그인까지 합니다."""
    clients = []

    def factory(kakao_id: int | None = None, nickname: str | None = None) -> TestClient:
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        if kakao_id is not None:
            kakao_login(client, kakao_id, nickname or f"user{kakao_id}")
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)
