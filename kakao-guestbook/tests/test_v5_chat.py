"""v5.0 스모크 테스트: 채팅방 개설, 친구만 초대, 초대 수락/거절, 메시지·파일, 읽음 수, 안 읽은 배지, 멘션."""

import re

from sqlalchemy import select

from app.database import SessionLocal
from app.models import ChatMember, ChatMessage, ChatRoom, Notification, User

from .conftest import AJAX


def uid(kakao_id: int) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.kakao_id == kakao_id))


def make_friends(a, b, a_kakao, b_kakao):
    a.post(f"/friends/request/{uid(b_kakao)}", headers=AJAX)
    b.post(f"/friends/request/{uid(a_kakao)}", headers=AJAX)  # 역방향 요청 → 자동 수락


def notif(kakao_id: int, type_: str) -> list[Notification]:
    with SessionLocal() as db:
        return list(db.scalars(select(Notification).where(Notification.user_id == uid(kakao_id), Notification.type == type_)))


def create_room(client, name, invitees=()) -> int:
    r = client.post("/chat/rooms", data={"name": name, "invitees": [str(i) for i in invitees]}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return int(r.headers["location"].rsplit("/", 1)[1])


def send(client, room_id, content="", files=None):
    return client.post(f"/chat/{room_id}/messages", data={"content": content}, files=files, headers=AJAX)


def setup_room(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    c = make_client(3, "씨")
    make_friends(a, b, 1, 2)
    make_friends(a, c, 1, 3)
    room = create_room(a, "우리 방", [uid(2), uid(3)])
    b.post(f"/chat/{room}/accept")
    c.post(f"/chat/{room}/accept")
    return a, b, c, room


def test_create_room_invite_only_friends(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    stranger = make_client(3, "모르는사람")
    make_friends(a, b, 1, 2)

    # 친구가 아닌 사람은 초대 불가 → 방도 만들어지지 않음
    r = a.post("/chat/rooms", data={"name": "방", "invitees": [str(uid(3))]}, headers=AJAX)
    assert r.status_code == 403
    with SessionLocal() as db:
        assert db.scalar(select(ChatRoom)) is None

    assert a.post("/chat/rooms", data={"name": "  "}, headers=AJAX).status_code == 400

    room = create_room(a, "친구 방", [uid(2)])
    with SessionLocal() as db:
        statuses = {m.user_id: m.status for m in db.scalars(select(ChatMember).where(ChatMember.room_id == room))}
    assert statuses == {uid(1): "joined", uid(2): "invited"}
    [n] = notif(2, "chat_invite")
    assert "친구 방" in n.message

    # 초대받은 사람은 수락 전 입장 불가, 목록에는 초대 표시
    assert b.get(f"/chat/{room}", headers=AJAX).status_code == 403
    assert f'id="invite-{room}"' in b.get("/chat").text
    assert stranger.get(f"/chat/{room}", headers=AJAX).status_code == 404

    # 알림 클릭 → 초대 목록으로
    assert b.get(f"/notifications/{n.id}/go", follow_redirects=False).headers["location"] == f"/chat?highlight=invite-{room}#invite-{room}"

    b.post(f"/chat/{room}/accept")
    assert b.get(f"/chat/{room}").status_code == 200
    assert "비님이 입장했습니다" in a.get(f"/chat/{room}").text
    assert [x.type for x in notif(1, "chat_invite")] == ["chat_invite"]  # 초대한 사람에게 수락 알림


def test_reject_invite_and_invite_later(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    make_friends(a, b, 1, 2)
    room = create_room(a, "방")
    assert a.post(f"/chat/{room}/invite", data={"invitees": [str(uid(2))]}, headers=AJAX).json()["ok"]
    b.post(f"/chat/{room}/reject", headers=AJAX)
    with SessionLocal() as db:
        assert db.scalar(select(ChatMember).where(ChatMember.user_id == uid(2))) is None
    assert "거절했습니다" in notif(1, "chat_invite")[-1].message
    assert b.post(f"/chat/{room}/accept", headers=AJAX).status_code == 404


def test_messages_read_counts_and_unread_badges(make_client):
    a, b, c, room = setup_room(make_client)

    r = send(a, room, "안녕하세요").json()
    assert r["ok"] and f'id="msg-{r["id"]}"' in r["html"]
    msg_id = r["id"]
    assert send(a, room, "   ").status_code == 400
    assert send(a, room, "x" * 2001).status_code == 400

    # 비·씨는 아직 안 읽음 → 채팅 목록 배지 1, 상단 메뉴 배지
    list_b = b.get("/chat").text
    assert re.search(rf'id="room-{room}".*?class="badge inline unread"\s*>1<', list_b, re.S)
    assert 'id="chat-badge">1<' in b.get("/").text

    # 비가 방에 들어오면 읽음 처리 → 에이 화면에서 "1명 읽음"
    b.get(f"/chat/{room}")
    page_a = a.get(f"/chat/{room}").text
    assert re.search(rf'id="msg-{msg_id}".*?1명 읽음', page_a, re.S)
    assert re.search(rf'id="room-{room}".*?class="badge inline unread"\s*hidden\s*>0<', b.get("/chat").text, re.S)

    c.post(f"/chat/{room}/read")
    assert re.search(rf'id="msg-{msg_id}".*?2명 읽음', a.get(f"/chat/{room}").text, re.S)

    # 놓친 메시지 API
    items = b.get(f"/chat/{room}/messages", params={"after": msg_id - 1}).json()["items"]
    assert [i["id"] for i in items] == [msg_id]


def test_file_upload_download_members_only(make_client, tmp_path):
    a, b, c, room = setup_room(make_client)
    outsider = make_client(9, "외부인")

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = send(a, room, "사진", files={"file": ("사진 1.png", png, "image/png")}).json()
    assert r["ok"] and "사진 1.png" in r["html"] and "chat-img" in r["html"]
    fid = r["id"]

    r = b.get(f"/chat/files/{fid}")
    assert r.status_code == 200 and r.content == png
    assert r.headers["content-type"] == "application/octet-stream"
    assert "attachment" in r.headers["content-disposition"]
    r = b.get(f"/chat/files/{fid}", params={"inline": 1})
    assert r.headers["content-type"] == "image/png" and r.headers["content-disposition"].startswith("inline")

    # 멤버가 아니면 다운로드 불가
    assert outsider.get(f"/chat/files/{fid}", headers=AJAX).status_code == 404

    # HTML/SVG 같은 파일은 인라인 표시 금지(항상 다운로드)
    r = send(a, room, files={"file": ("x.svg", b"<svg onload=alert(1)>", "image/svg+xml")}).json()
    svg = b.get(f"/chat/files/{r['id']}", params={"inline": 1})
    assert svg.headers["content-type"] == "application/octet-stream" and "attachment" in svg.headers["content-disposition"]

    # 크기 제한(테스트 설정 1MB): 저장 단계 검사 + Content-Length 사전 차단
    big = b"0" * (1024 * 1024 + 10)
    r = send(a, room, files={"file": ("big.bin", big, "application/octet-stream")})
    assert r.status_code == 413
    huge = b"0" * (3 * 1024 * 1024)
    r = send(a, room, files={"file": ("huge.bin", huge, "application/octet-stream")})
    assert r.status_code == 413
    with SessionLocal() as db:
        assert db.scalar(select(ChatMessage).where(ChatMessage.file_name == "big.bin")) is None


def test_mentions_notify_and_navigate(make_client):
    a, b, c, room = setup_room(make_client)
    b.post("/me", data={"display_name": "비 디자이너", "bio": ""})

    r = send(a, room, "@비 디자이너 확인 부탁해요! @씨 도요").json()
    assert '<span class="mention">@비 디자이너</span>' in r["html"]
    [nb] = notif(2, "mention")
    [nc] = notif(3, "mention")
    assert "언급했습니다" in nb.message and nc.target_id == r["id"]
    assert notif(1, "mention") == []

    loc = b.get(f"/notifications/{nb.id}/go", follow_redirects=False).headers["location"]
    assert loc == f"/chat/{room}?highlight=msg-{r['id']}#msg-{r['id']}"

    send(a, room, "@에이 본인 멘션은 알림 없음")
    assert notif(1, "mention") == []


def test_leave_room_and_cleanup(make_client):
    a, b, c, room = setup_room(make_client)
    send(a, room, files={"file": ("a.txt", b"hello", "text/plain")})
    b.post(f"/chat/{room}/leave")
    assert "비님이 나갔습니다" in a.get(f"/chat/{room}").text
    assert b.get(f"/chat/{room}", headers=AJAX).status_code == 404
    a.post(f"/chat/{room}/leave")
    c.post(f"/chat/{room}/leave")  # 마지막 멤버가 나가면 방 삭제
    with SessionLocal() as db:
        assert db.get(ChatRoom, room) is None
        assert db.scalar(select(ChatMessage)) is None
