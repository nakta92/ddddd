"""v2.0 스모크 테스트: 내 정보(표시 이름/자기소개), 관리자 페이지, 최초 관리자 지정, 기본 관리자 로그인."""

from sqlalchemy import func, select

from app.config import settings
from app.database import SessionLocal
from app.models import Post, User

from .conftest import AJAX, kakao_login


def get_user(kakao_id: int | None = None, username: str | None = None) -> User | None:
    with SessionLocal() as db:
        if kakao_id is not None:
            return db.scalar(select(User).where(User.kakao_id == kakao_id))
        return db.scalar(select(User).where(User.username == username))


def test_display_name_takes_priority(make_client):
    a = make_client(1, "카카오닉")
    a.get("/")  # 로그인 환영 플래시 메시지 소비
    a.post("/posts", data={"content": "글"}, headers=AJAX)

    r = a.post("/me", data={"display_name": "  멋진   이름 ", "bio": "안녕하세요\n반가워요"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/me"
    user = get_user(1)
    assert user.display_name == "멋진 이름" and user.bio == "안녕하세요\n반가워요"

    home = a.get("/").text
    assert "멋진 이름" in home
    assert "카카오닉" not in home  # 작성자·상단바 모두 표시 이름 사용

    profile = a.get(f"/users/{user.id}").text
    assert "안녕하세요" in profile and "멋진 이름" in profile

    # 비우면 카카오 닉네임으로 복귀, 카카오 재로그인해도 표시 이름은 유지
    a.post("/me", data={"display_name": "", "bio": ""})
    assert get_user(1).display_name is None
    assert "카카오닉" in a.get("/").text
    a.post("/me", data={"display_name": "유지될 이름", "bio": ""})
    kakao_login(a, 1, "새카카오닉")
    assert get_user(1).name == "유지될 이름"


def test_my_info_validation(make_client):
    a = make_client(1, "A")
    assert a.post("/me", data={"display_name": "x" * 31, "bio": ""}, headers=AJAX).status_code == 400
    assert a.post("/me", data={"display_name": "a@b", "bio": ""}, headers=AJAX).status_code == 400
    assert a.post("/me", data={"display_name": "ok", "bio": "x" * 301}, headers=AJAX).status_code == 400
    assert make_client().get("/me", follow_redirects=False).headers["location"].startswith("/login")


def test_admin_page_requires_admin(make_client):
    anon = make_client()
    assert anon.get("/admin", follow_redirects=False).headers["location"].startswith("/login")
    normal = make_client(1, "일반")
    r = normal.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert normal.post("/admin/users/1/grant", headers=AJAX).status_code == 403


def test_initial_admin_from_env(make_client, monkeypatch):
    monkeypatch.setattr(settings, "admin_kakao_ids", "777, 888")
    boss = make_client(777, "대표")
    assert get_user(777).is_admin
    assert boss.get("/admin").status_code == 200
    make_client(5, "일반")
    assert not get_user(5).is_admin


def test_admin_manage_members(make_client, monkeypatch):
    monkeypatch.setattr(settings, "admin_kakao_ids", "777")
    boss = make_client(777, "대표")
    member = make_client(2, "회원")
    member.post("/posts", data={"content": "회원의 글"}, headers=AJAX)
    me_id, member_id = get_user(777).id, get_user(2).id

    page = boss.get("/admin").text
    assert "회원" in page and f'id="user-row-{member_id}"' in page

    # 권한 부여 / 해제 (행 HTML 부분 교체)
    r = boss.post(f"/admin/users/{member_id}/grant", headers=AJAX).json()
    assert r["replace"][0]["id"] == f"user-row-{member_id}" and "권한 해제" in r["replace"][0]["html"]
    assert get_user(2).is_admin
    boss.post(f"/admin/users/{member_id}/revoke", headers=AJAX)
    assert not get_user(2).is_admin

    # 본인 해제·삭제 차단
    assert boss.post(f"/admin/users/{me_id}/revoke", headers=AJAX).status_code == 400
    assert boss.post(f"/admin/users/{me_id}/delete", headers=AJAX).status_code == 400
    assert get_user(777).is_admin

    # 회원 삭제 → 글도 함께 삭제, 삭제된 회원의 세션은 비로그인 처리
    r = boss.post(f"/admin/users/{member_id}/delete", headers=AJAX).json()
    assert r["removed"] == f"user-row-{member_id}"
    assert get_user(2) is None
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Post.id))) == 0
    assert member.post("/posts", data={"content": "x"}, headers=AJAX).status_code == 401

    # 검색
    make_client(3, "검색될사람")
    assert "검색될사람" in boss.get("/admin", params={"q": "검색될"}).text
    assert "검색될사람" not in boss.get("/admin", params={"q": "없는이름"}).text


def test_default_admin_account_login(make_client, monkeypatch):
    client = make_client()
    # 설정이 없으면 비활성
    r = client.post("/auth/admin/login", data={"username": "admin", "password": "x"}, follow_redirects=False)
    assert r.headers["location"] == "/auth/admin/login" and get_user(username="admin") is None

    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "s3cret-pass")
    assert "관리자 계정으로 로그인" in client.get("/login").text

    r = client.post("/auth/admin/login", data={"username": "admin", "password": "wrong"}, follow_redirects=False)
    assert r.headers["location"] == "/auth/admin/login"
    assert get_user(username="admin") is None

    r = client.post("/auth/admin/login", data={"username": "admin", "password": "s3cret-pass"}, follow_redirects=False)
    assert r.headers["location"] == "/admin"
    admin = get_user(username="admin")
    assert admin.is_admin and admin.kakao_id is None
    assert client.get("/admin").status_code == 200

    # 기본 관리자도 글 작성 가능
    assert client.post("/posts", data={"content": "공지"}, headers=AJAX).json()["ok"]


def test_admin_login_throttled(make_client, monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "s3cret-pass")
    client = make_client()
    for _ in range(5):
        client.post("/auth/admin/login", data={"username": "admin", "password": "bad"})
    client.post("/auth/admin/login", data={"username": "admin", "password": "s3cret-pass"})
    assert get_user(username="admin") is None  # 5회 실패 후 잠금
