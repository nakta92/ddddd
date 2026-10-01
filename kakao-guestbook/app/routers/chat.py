import asyncio
import json
import time

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import chat as svc
from ..config import settings
from ..database import SessionLocal, get_db
from ..deps import AppError, LoginRequired, flash, login_required, render, templates, wants_json
from ..friends import friend_ids, relation_map
from ..models import ChatMember, ChatMessage, ChatRoom, User, utcnow
from ..notify import notify, snippet
from ..pubsub import broker

router = APIRouter(prefix="/chat")

SSE_PING_SECONDS = 15
SSE_MAX_SECONDS = 600  # 오래 열린 연결은 정리하고 EventSource가 자동 재연결


# ---------- 공통 ----------

def require_joined(db: Session, room_id: int, user: User) -> ChatMember:
    member = svc.get_membership(db, room_id, user.id)
    if member is None:
        raise AppError("채팅방을 찾을 수 없거나 멤버가 아닙니다.", 404, redirect_to="/chat")
    if member.status != "joined":
        raise AppError("초대를 수락해야 채팅방에 들어갈 수 있습니다.", 403, redirect_to="/chat")
    return member


def invite_friends(db: Session, room: ChatRoom, inviter: User, user_ids: list[int]) -> list[User]:
    """사이 맺은 친구만 초대합니다. 이미 멤버/초대된 사람은 건너뜁니다."""
    friends = friend_ids(db, inviter.id)
    invited: list[User] = []
    for uid in dict.fromkeys(user_ids):  # 중복 제거(순서 유지)
        if uid not in friends:
            raise AppError("사이 맺은 친구만 초대할 수 있습니다.", 403, redirect_to=f"/chat/{room.id}")
        if svc.get_membership(db, room.id, uid):
            continue
        target = db.get(User, uid)
        if target is None:
            continue
        member = ChatMember(room_id=room.id, user_id=uid, status="invited", invited_by_id=inviter.id)
        db.add(member)
        notify(db, uid, inviter, "chat_invite",
               f"{inviter.name}님이 채팅방 '{room.name}'에 초대했습니다.", "chat_room", room.id)
        invited.append(target)
    return invited


def sse_format(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def sse_response(request: Request, channel: str, ready: dict) -> StreamingResponse:
    """채널 구독 SSE 스트림. DB 세션을 붙잡지 않도록 인증·권한 확인은 호출 전에 끝냅니다."""
    sub = broker.subscribe(channel)

    async def stream():
        started = time.monotonic()
        try:
            yield "retry: 3000\n\n"
            yield sse_format({"type": "ready", **ready})
            while time.monotonic() - started < SSE_MAX_SECONDS:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(sub.queue.get(), timeout=SSE_PING_SECONDS)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield sse_format(event)
        finally:
            broker.unsubscribe(sub)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def session_user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not user_id:
        raise LoginRequired()
    return user_id


# ---------- 채팅 목록 / 방 만들기 / 초대 응답 ----------

@router.get("")
def chat_list(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    memberships = list(db.scalars(select(ChatMember).where(ChatMember.user_id == user.id)))
    joined = [m for m in memberships if m.status == "joined"]
    invites = [m for m in memberships if m.status == "invited"]
    unread = svc.unread_by_room(db, user.id)

    rooms = []
    for m in joined:
        last = db.scalar(
            select(ChatMessage).where(ChatMessage.room_id == m.room_id).order_by(ChatMessage.id.desc()).limit(1)
        )
        member_count = db.scalar(
            select(func.count(ChatMember.id)).where(ChatMember.room_id == m.room_id, ChatMember.status == "joined")
        )
        rooms.append({"room": m.room, "last": last, "unread": unread.get(m.room_id, 0), "members": member_count})
    rooms.sort(key=lambda r: (r["last"].id if r["last"] else 0), reverse=True)

    friends = [db.get(User, uid) for uid in sorted(friend_ids(db, user.id))]
    return render(request, "chat_list.html", user, db, rooms=rooms, invites=invites,
                  friends=[f for f in friends if f], name_max=svc.ROOM_NAME_MAX)


@router.post("/rooms")
def create_room(request: Request, name: str = Form(""), invitees: list[int] = Form([]),
                db: Session = Depends(get_db), user: User = Depends(login_required)):
    name = " ".join(name.split())
    if not name or len(name) > svc.ROOM_NAME_MAX:
        raise AppError(f"방 이름을 1~{svc.ROOM_NAME_MAX}자로 입력해 주세요.", redirect_to="/chat")
    room = ChatRoom(name=name, owner_id=user.id)
    db.add(room)
    db.flush()
    db.add(ChatMember(room_id=room.id, user_id=user.id, status="joined", joined_at=utcnow()))
    svc.add_system_message(db, room.id, f"{user.name}님이 채팅방을 만들었습니다.")
    invited = invite_friends(db, room, user, invitees)
    db.commit()
    for u in invited:
        broker.publish(f"user:{u.id}", {"type": "invite", "room_id": room.id})
    if wants_json(request):
        return JSONResponse({"ok": True, "redirect": f"/chat/{room.id}"})
    return RedirectResponse(f"/chat/{room.id}", status_code=303)


@router.get("/events")
async def user_events(request: Request):
    """채팅 목록 화면용 개인 채널: 방별 안 읽은 수 / 새 초대."""
    user_id = session_user_id(request)
    return sse_response(request, f"user:{user_id}", {"user_id": user_id})


@router.get("/files/{message_id}")
def download_file(message_id: int, inline: bool = False, db: Session = Depends(get_db),
                  user: User = Depends(login_required)):
    msg = db.get(ChatMessage, message_id)
    if msg is None or msg.kind != "file":
        raise AppError("파일을 찾을 수 없습니다.", 404, redirect_to="/chat")
    require_joined(db, msg.room_id, user)  # 멤버만 다운로드
    path = svc.file_path_of(msg)
    if path is None or not path.is_file():
        raise AppError("파일이 서버에 없습니다.", 404, redirect_to=f"/chat/{msg.room_id}")
    show_inline = inline and svc.is_inline_image(msg)
    return FileResponse(
        path,
        media_type=msg.file_mime if show_inline else "application/octet-stream",
        filename=msg.file_name,
        content_disposition_type="inline" if show_inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"},
    )


@router.post("/{room_id}/accept")
def accept_invite(request: Request, room_id: int, db: Session = Depends(get_db),
                  user: User = Depends(login_required)):
    member = svc.get_membership(db, room_id, user.id)
    if member is None or member.status != "invited":
        raise AppError("수락할 초대가 없습니다.", 404, redirect_to="/chat")
    member.status = "joined"
    member.joined_at = utcnow()
    msg = svc.add_system_message(db, room_id, f"{user.name}님이 입장했습니다.")
    if member.invited_by_id:
        notify(db, member.invited_by_id, user, "chat_invite",
               f"{user.name}님이 채팅방 '{member.room.name}' 초대를 수락했습니다.", "chat_room", room_id)
    svc.mark_read(db, member)
    db.commit()
    svc.publish_message(db, msg)
    svc.publish_members(db, room_id)
    if wants_json(request):
        return JSONResponse({"ok": True, "redirect": f"/chat/{room_id}"})
    return RedirectResponse(f"/chat/{room_id}", status_code=303)


@router.post("/{room_id}/reject")
def reject_invite(request: Request, room_id: int, db: Session = Depends(get_db),
                  user: User = Depends(login_required)):
    member = svc.get_membership(db, room_id, user.id)
    if member is None or member.status != "invited":
        raise AppError("거절할 초대가 없습니다.", 404, redirect_to="/chat")
    room_name = member.room.name
    if member.invited_by_id:
        notify(db, member.invited_by_id, user, "chat_invite",
               f"{user.name}님이 채팅방 '{room_name}' 초대를 거절했습니다.", "chat_room", room_id)
    db.delete(member)
    db.commit()
    svc.publish_members(db, room_id)
    message = f"'{room_name}' 초대를 거절했습니다."
    if wants_json(request):
        flash(request, message, "success")
        return JSONResponse({"ok": True, "reload": True})
    flash(request, message, "success")
    return RedirectResponse("/chat", status_code=303)


# ---------- 채팅방 ----------

@router.get("/{room_id}")
def chat_room(request: Request, room_id: int, highlight: str = "", db: Session = Depends(get_db),
              user: User = Depends(login_required)):
    me = require_joined(db, room_id, user)
    room = me.room

    stmt = select(ChatMessage).where(ChatMessage.room_id == room_id)
    # 알림으로 들어온 오래된 메시지도 보이도록 범위를 넓힙니다.
    target_id = int(highlight[4:]) if highlight.startswith("msg-") and highlight[4:].isdigit() else None
    recent = list(db.scalars(stmt.order_by(ChatMessage.id.desc()).limit(svc.HISTORY_LIMIT)))
    if target_id and recent and target_id < recent[-1].id:
        recent = list(db.scalars(stmt.where(ChatMessage.id >= target_id - 20).order_by(ChatMessage.id.desc())))
    messages = list(reversed(recent))
    has_older = bool(messages) and db.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.room_id == room_id, ChatMessage.id < messages[0].id)
    ) > 0

    if svc.mark_read(db, me):  # 방 입장 시 읽음 처리
        db.commit()
        svc.publish_read(me)

    members = svc.joined_members(db, room_id)
    readers = svc.readers_map(members)
    names = [m.user.name for m in members]
    my_friends = friend_ids(db, user.id)
    member_ids = {m.user_id for m in members} | {m.user_id for m in svc.invited_members(db, room_id)}
    invitable = [db.get(User, uid) for uid in sorted(my_friends - member_ids)]
    return render(
        request, "chat_room.html", user, db,
        room=room, messages=messages, has_older=has_older,
        reads=svc.read_counts(messages, readers), mention_names=names, me_id=user.id,
        members=members, invited=svc.invited_members(db, room_id),
        relations=relation_map(db, user.id), invitable=[u for u in invitable if u],
        chat_data={
            "room_id": room_id,
            "me": user.id,
            "members": [{"id": m.user_id, "name": m.user.name} for m in members],
            "readers": {str(k): v for k, v in readers.items()},
            "max_upload_mb": settings.max_upload_mb,
        },
        max_upload_mb=settings.max_upload_mb,
    )


@router.get("/{room_id}/members")
def room_members_fragment(request: Request, room_id: int, db: Session = Depends(get_db),
                          user: User = Depends(login_required)):
    require_joined(db, room_id, user)
    members = svc.joined_members(db, room_id)
    html = templates.get_template("_chat_members.html").render({
        "request": request, "user": user, "members": members, "invited": svc.invited_members(db, room_id),
        "relations": relation_map(db, user.id),
    })
    return JSONResponse({
        "html": html,
        "members": [{"id": m.user_id, "name": m.user.name} for m in members],
        "readers": {str(k): v for k, v in svc.readers_map(members).items()},
    })


@router.get("/{room_id}/messages")
def messages_after(room_id: int, after: int = 0, db: Session = Depends(get_db), user: User = Depends(login_required)):
    """실시간 연결이 끊겼다 다시 붙었을 때 놓친 메시지를 가져옵니다."""
    require_joined(db, room_id, user)
    msgs = list(db.scalars(
        select(ChatMessage)
        .where(ChatMessage.room_id == room_id, ChatMessage.id > after)
        .order_by(ChatMessage.id)
        .limit(svc.HISTORY_LIMIT)
    ))
    members = svc.joined_members(db, room_id)
    names = [m.user.name for m in members]
    reads = svc.read_counts(msgs, svc.readers_map(members))
    return {"items": [{"id": m.id, "html": svc.message_html(m, names, reads, user.id)} for m in msgs]}


@router.get("/{room_id}/events")
async def room_events(request: Request, room_id: int):
    user_id = session_user_id(request)
    with SessionLocal() as db:  # 짧게 열고 바로 닫아 스트림 동안 DB 연결을 잡지 않음
        member = svc.get_membership(db, room_id, user_id)
        if member is None or member.status != "joined":
            return JSONResponse({"ok": False, "error": "채팅방 멤버가 아닙니다."}, 403)
    return sse_response(request, f"room:{room_id}", {"room_id": room_id})


@router.post("/{room_id}/messages")
def send_message(request: Request, room_id: int, content: str = Form(""),
                 file: UploadFile | None = File(None), db: Session = Depends(get_db),
                 user: User = Depends(login_required)):
    me = require_joined(db, room_id, user)
    content = content.strip()
    has_file = file is not None and bool(file.filename)
    if not content and not has_file:
        raise AppError("메시지나 파일을 입력해 주세요.", redirect_to=f"/chat/{room_id}")
    if len(content) > svc.MESSAGE_MAX_LEN:
        raise AppError(f"메시지는 {svc.MESSAGE_MAX_LEN}자 이하로 입력해 주세요.", redirect_to=f"/chat/{room_id}")

    msg = ChatMessage(room_id=room_id, user_id=user.id, kind="text", content=content or None)
    if has_file:
        rel_path, size = svc.save_upload(file, room_id)
        filename = (file.filename or "file").replace("/", "_").replace("\\", "_")[-200:]
        msg.kind = "file"
        msg.file_name = filename
        msg.file_path = rel_path
        msg.file_size = size
        msg.file_mime = svc.guess_mime(filename)
    db.add(msg)
    db.flush()

    members = svc.joined_members(db, room_id)
    if content:
        for target in svc.find_mentions(content, members, user.id):
            notify(db, target.id, user, "mention",
                   f"{user.name}님이 '{me.room.name}'에서 회원님을 언급했습니다: “{snippet(content)}”",
                   "chat_message", msg.id)
    me.last_read_message_id = msg.id  # 내가 보낸 메시지까지는 읽은 것
    db.commit()

    svc.publish_message(db, msg)
    if wants_json(request):
        names = [m.user.name for m in members]
        return JSONResponse({"ok": True, "id": msg.id, "html": svc.message_html(msg, names, {msg.id: 0}, user.id)})
    return RedirectResponse(f"/chat/{room_id}#msg-{msg.id}", status_code=303)


@router.post("/{room_id}/read")
def mark_room_read(room_id: int, db: Session = Depends(get_db), user: User = Depends(login_required)):
    me = require_joined(db, room_id, user)
    if svc.mark_read(db, me):
        db.commit()
        svc.publish_read(me)
    return {"ok": True, "last_read": me.last_read_message_id}


@router.post("/{room_id}/invite")
def invite_to_room(request: Request, room_id: int, invitees: list[int] = Form([]),
                   db: Session = Depends(get_db), user: User = Depends(login_required)):
    me = require_joined(db, room_id, user)
    if not invitees:
        raise AppError("초대할 친구를 선택해 주세요.", redirect_to=f"/chat/{room_id}")
    invited = invite_friends(db, me.room, user, invitees)
    if invited:
        msg = svc.add_system_message(db, room_id, f"{user.name}님이 {', '.join(u.name for u in invited)}님을 초대했습니다.")
    db.commit()
    for u in invited:
        broker.publish(f"user:{u.id}", {"type": "invite", "room_id": room_id})
    if invited:
        svc.publish_message(db, msg)
        svc.publish_members(db, room_id)
    message = f"{len(invited)}명을 초대했습니다. 수락하면 입장합니다." if invited else "이미 초대된 친구입니다."
    flash(request, message, "success")
    if wants_json(request):
        return JSONResponse({"ok": True, "reload": True})
    return RedirectResponse(f"/chat/{room_id}", status_code=303)


@router.post("/{room_id}/leave")
def leave_room(request: Request, room_id: int, db: Session = Depends(get_db), user: User = Depends(login_required)):
    me = require_joined(db, room_id, user)
    room_name = me.room.name
    db.delete(me)
    db.flush()
    remaining = svc.joined_members(db, room_id)
    msg = None
    if remaining:
        msg = svc.add_system_message(db, room_id, f"{user.name}님이 나갔습니다.")
    else:  # 마지막 멤버가 나가면 방과 첨부파일 삭제
        db.delete(db.get(ChatRoom, room_id))
    db.commit()
    if msg:
        svc.publish_message(db, msg)
        svc.publish_members(db, room_id)
    else:
        svc.delete_room_files(room_id)
    flash(request, f"'{room_name}' 채팅방에서 나왔습니다.", "success")
    if wants_json(request):
        return JSONResponse({"ok": True, "redirect": "/chat"})
    return RedirectResponse("/chat", status_code=303)
