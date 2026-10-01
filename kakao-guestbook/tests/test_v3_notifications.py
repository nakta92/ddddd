"""v3.0 스모크 테스트: 댓글/대댓글/반응 알림, 목록·배지, 클릭 시 대상 이동+강조, 모두 읽음."""

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Notification, User

from .conftest import AJAX


def uid(kakao_id: int) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.kakao_id == kakao_id))


def notifications_of(kakao_id: int) -> list[Notification]:
    with SessionLocal() as db:
        return list(db.scalars(select(Notification).where(Notification.user_id == uid(kakao_id)).order_by(Notification.id)))


def new_post(client, content="글") -> int:
    return client.post("/posts", data={"content": content}, headers=AJAX).json()["post_id"]


def new_comment(client, pid, content="댓글", parent_id=None) -> int:
    data = {"content": content}
    if parent_id:
        data["parent_id"] = str(parent_id)
    r = client.post(f"/posts/{pid}/comments", data=data, headers=AJAX).json()
    return int(r["focus"].split("-")[1])


def test_comment_and_reply_notifications(make_client):
    a = make_client(1, "에이")  # 글 작성자
    b = make_client(2, "비")
    c = make_client(3, "씨")
    pid = new_post(a, "에이의 글")

    new_comment(a, pid, "내 글에 내가 단 댓글")  # 본인 → 알림 없음
    assert notifications_of(1) == []

    cid = new_comment(b, pid, "비의 댓글")
    [n] = notifications_of(1)
    assert n.type == "comment" and "비님이 회원님의 글에 댓글" in n.message and "비의 댓글" in n.message
    assert n.target_type == "comment" and n.target_id == cid and not n.is_read

    new_comment(c, pid, "씨의 답글", parent_id=cid)
    assert [x.type for x in notifications_of(2)] == ["reply"]  # 댓글 작성자에게 답글 알림
    assert [x.type for x in notifications_of(1)] == ["comment", "comment"]  # 글 작성자에게도


def test_reaction_notifications_dedupe(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    pid = new_post(a, "반응 받을 글")

    b.post(f"/posts/{pid}/react", data={"kind": "like"}, headers=AJAX)
    [n] = notifications_of(1)
    assert n.type == "reaction" and "👍 좋아요" in n.message

    b.post(f"/posts/{pid}/react", data={"kind": "like"}, headers=AJAX)    # 취소 → 알림 추가 없음
    b.post(f"/posts/{pid}/react", data={"kind": "thanks"}, headers=AJAX)  # 안 읽은 알림 갱신(중복 방지)
    [n] = notifications_of(1)
    assert "🙏 감사해요" in n.message

    a.post(f"/posts/{pid}/react", data={"kind": "like"}, headers=AJAX)    # 내 글에 내 반응 → 알림 없음
    assert len(notifications_of(1)) == 1

    cid = new_comment(a, pid, "에이의 댓글")
    b.post(f"/comments/{cid}/react", data={"kind": "dislike"}, headers=AJAX)
    assert notifications_of(1)[-1].target_type == "comment"


def test_list_badge_go_and_read_all(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    a.get("/")  # 환영 메시지 소비
    pid = new_post(a)
    cid = new_comment(b, pid, "첫 댓글")
    new_comment(b, pid, "둘째 댓글")

    page = a.get("/").text
    assert 'id="notif-badge"' in page and ">2</span>" in page
    assert a.get("/notifications/unread-count").json() == {"count": 2}

    listing = a.get("/notifications").text
    assert listing.count('class="notif unread"') == 2

    first = notifications_of(1)[0]
    r = a.get(f"/notifications/{first.id}/go", follow_redirects=False)
    assert r.headers["location"] == f"/?page=1&highlight=comment-{cid}#comment-{cid}"
    assert notifications_of(1)[0].is_read
    listing = a.get("/notifications").text
    assert listing.count('class="notif unread"') == 1 and listing.count('class="notif read"') == 1

    # 남의 알림은 열 수 없음
    assert b.get(f"/notifications/{first.id}/go", headers=AJAX).status_code == 404

    a.post("/notifications/read-all", headers=AJAX)
    assert a.get("/notifications/unread-count").json() == {"count": 0}
    assert 'id="notif-badge" hidden' in a.get("/").text


def test_go_to_deleted_target(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    pid = new_post(a)
    cid = new_comment(b, pid)
    b.post(f"/comments/{cid}/delete", headers=AJAX)
    [n] = notifications_of(1)
    r = a.get(f"/notifications/{n.id}/go", follow_redirects=False)
    assert r.headers["location"] == "/notifications"
    assert "삭제되었거나" in a.get("/notifications").text


def test_notifications_cleanup_on_user_delete(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    pid = new_post(a)
    new_comment(b, pid)
    with SessionLocal() as db:
        db.delete(db.get(User, uid(2)))  # 알림을 만든 사람 삭제 → 알림은 남고 actor만 비움
        db.commit()
    [n] = notifications_of(1)
    assert n.actor_id is None
    assert "notif" in a.get("/notifications").text
