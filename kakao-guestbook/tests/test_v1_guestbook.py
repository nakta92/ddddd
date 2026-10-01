"""v1.0 스모크 테스트: 카카오 로그인, 방명록 글/댓글/대댓글, 반응, AJAX/리다이렉트, 페이지네이션, KST."""

import re
from datetime import datetime

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Comment, Post, Reaction, User
from app.timeutil import format_kst

from .conftest import AJAX, kakao_login


def count(model) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model))


def test_kst_format():
    # UTC 15:30 -> KST 다음 날 00:30
    assert format_kst(datetime(2026, 1, 1, 15, 30)) == "2026-01-02 00:30"
    assert format_kst(None) == ""


def test_home_is_public(make_client):
    r = make_client().get("/")
    assert r.status_code == 200
    assert "카카오 로그인" in r.text
    assert "아직 작성된 글이 없어요" in r.text


def test_kakao_login_upserts_user(make_client):
    client = make_client()
    kakao_login(client, 1001, "철수", "https://img.example/1.png")
    kakao_login(client, 1001, "철수(변경)")
    with SessionLocal() as db:
        users = db.scalars(select(User)).all()
    assert len(users) == 1
    user = users[0]
    assert user.kakao_id == 1001 and user.nickname == "철수(변경)"
    assert user.created_at is not None and user.last_login_at is not None
    assert "철수(변경)" in client.get("/").text


def test_login_rejects_bad_state(make_client):
    client = make_client()
    client.get("/auth/kakao/login", follow_redirects=False)
    r = client.get("/auth/kakao/callback", params={"code": "x", "state": "wrong"}, follow_redirects=False)
    assert r.headers["location"] == "/login"
    assert count(User) == 0


def test_login_next_and_open_redirect_blocked(make_client):
    client = make_client()
    r = kakao_login(client, 1, "A", next_path="/?page=2")
    assert r.headers["location"] == "/?page=2"
    r = kakao_login(client, 1, "A", next_path="//evil.example.com")
    assert r.headers["location"] == "/"


def test_logout(make_client):
    client = make_client(1, "A")
    client.post("/auth/logout")
    r = client.post("/posts", data={"content": "x"}, headers=AJAX)
    assert r.status_code == 401


def test_write_requires_login(make_client):
    client = make_client()
    r = client.post("/posts", data={"content": "hi"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    r = client.post("/posts", data={"content": "hi"}, headers=AJAX)
    assert r.status_code == 401 and r.json()["login"].startswith("/login")


def test_post_crud_ajax_and_fallback(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")

    r = a.post("/posts", data={"content": "안녕하세요\n반가워요"}, headers=AJAX)
    data = r.json()
    assert data["ok"] and data["focus"] == f"post-{data['post_id']}"
    assert f'id="post-{data["post_id"]}"' in data["html"]
    pid = data["post_id"]

    # JS 미사용(fallback): 리다이렉트로 글 위치 이동
    r = a.post("/posts", data={"content": "두 번째"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/?page=1")

    assert a.post("/posts", data={"content": "   "}, headers=AJAX).status_code == 400
    assert a.post("/posts", data={"content": "x" * 2001}, headers=AJAX).status_code == 400

    # 본인만 수정·삭제
    assert b.post(f"/posts/{pid}/edit", data={"content": "해킹"}, headers=AJAX).status_code == 403
    assert b.post(f"/posts/{pid}/delete", headers=AJAX).status_code == 403

    r = a.post(f"/posts/{pid}/edit", data={"content": "수정한 내용"}, headers=AJAX)
    assert "수정한 내용" in r.json()["html"] and "(수정됨)" in r.json()["html"]

    r = a.post(f"/posts/{pid}/delete", headers=AJAX)
    assert r.json()["removed"] == f"post-{pid}"
    assert count(Post) == 1


def test_html_is_escaped(make_client):
    a = make_client(1, "A")
    html = a.post("/posts", data={"content": "<script>alert(1)</script>"}, headers=AJAX).json()["html"]
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_comments_and_one_level_replies(make_client):
    a = make_client(1, "A")
    b = make_client(2, "B")
    pid = a.post("/posts", data={"content": "글"}, headers=AJAX).json()["post_id"]

    r = b.post(f"/posts/{pid}/comments", data={"content": "댓글"}, headers=AJAX).json()
    cid = int(r["focus"].split("-")[1])
    assert f'id="comment-{cid}"' in r["html"]

    r = a.post(f"/posts/{pid}/comments", data={"content": "답글", "parent_id": str(cid)}, headers=AJAX).json()
    reply_id = int(r["focus"].split("-")[1])

    # 대댓글에 다시 답글을 달면 원 댓글 아래로 붙음(1단계 유지)
    r = b.post(f"/posts/{pid}/comments", data={"content": "답글의 답글", "parent_id": str(reply_id)}, headers=AJAX).json()
    nested_id = int(r["focus"].split("-")[1])
    with SessionLocal() as db:
        assert db.get(Comment, reply_id).parent_id == cid
        assert db.get(Comment, nested_id).parent_id == cid
    assert "답글 2개" in r["html"]

    # 다른 글의 댓글을 부모로 지정할 수 없음
    other = a.post("/posts", data={"content": "다른 글"}, headers=AJAX).json()["post_id"]
    assert b.post(f"/posts/{other}/comments", data={"content": "x", "parent_id": str(cid)}, headers=AJAX).status_code == 404

    # 댓글 수정/삭제는 본인만
    assert a.post(f"/comments/{cid}/edit", data={"content": "남의 댓글"}, headers=AJAX).status_code == 403
    r = b.post(f"/comments/{cid}/edit", data={"content": "고친 댓글"}, headers=AJAX).json()
    assert "고친 댓글" in r["html"]

    # 원 댓글 삭제 시 대댓글도 함께 삭제(CASCADE)
    b.post(f"/comments/{cid}/delete", headers=AJAX)
    assert count(Comment) == 0


def test_reaction_toggle_and_names(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    pid = a.post("/posts", data={"content": "글"}, headers=AJAX).json()["post_id"]

    def my_reaction(user_kakao_id):
        with SessionLocal() as db:
            uid = db.scalar(select(User.id).where(User.kakao_id == user_kakao_id))
            return db.scalar(select(Reaction.kind).where(Reaction.user_id == uid, Reaction.post_id == pid))

    html = b.post(f"/posts/{pid}/react", data={"kind": "like"}, headers=AJAX).json()["html"]
    assert my_reaction(2) == "like"
    assert 'data-tip="좋아요: 비"' in html
    assert re.search(r'class="reaction mine"', html)

    b.post(f"/posts/{pid}/react", data={"kind": "like"}, headers=AJAX)  # 같은 반응 다시 -> 취소
    assert my_reaction(2) is None

    b.post(f"/posts/{pid}/react", data={"kind": "like"}, headers=AJAX)
    b.post(f"/posts/{pid}/react", data={"kind": "thanks"}, headers=AJAX)  # 다른 반응 -> 교체(1개 유지)
    assert my_reaction(2) == "thanks"
    html = a.post(f"/posts/{pid}/react", data={"kind": "thanks"}, headers=AJAX).json()["html"]
    assert 'data-tip="감사해요: 비, 에이"' in html
    assert count(Reaction) == 2

    assert b.post(f"/posts/{pid}/react", data={"kind": "angry"}, headers=AJAX).status_code == 400

    # 댓글·대댓글 반응
    cid = int(a.post(f"/posts/{pid}/comments", data={"content": "c"}, headers=AJAX).json()["focus"].split("-")[1])
    html = b.post(f"/comments/{cid}/react", data={"kind": "dislike"}, headers=AJAX).json()["html"]
    assert 'data-tip="싫어요: 비"' in html

    # 글 삭제 시 댓글·반응까지 CASCADE 삭제
    a.post(f"/posts/{pid}/delete", headers=AJAX)
    assert count(Reaction) == 0 and count(Comment) == 0


def test_pagination_and_permalink(make_client):
    a = make_client(1, "A")
    ids = [a.post("/posts", data={"content": f"글{i}"}, headers=AJAX).json()["post_id"] for i in range(7)]

    page1 = a.get("/").text
    page2 = a.get("/?page=2").text
    assert page1.count('class="post card"') == 5
    assert page2.count('class="post card"') == 2
    assert 'aria-current="page">2<' in page2
    assert a.get("/?page=99").text.count('class="post card"') == 2  # 범위 밖은 마지막 페이지

    r = a.get(f"/posts/{ids[0]}", follow_redirects=False)  # 가장 오래된 글은 2페이지
    assert r.headers["location"] == f"/?page=2#post-{ids[0]}"
