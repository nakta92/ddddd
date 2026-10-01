"""그룹 채팅 헬퍼: 멤버십·읽음 처리·안 읽은 수·멘션·첨부파일·실시간 이벤트."""

import mimetypes
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from markupsafe import Markup, escape
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .deps import AppError, templates
from .models import ChatMember, ChatMessage, User
from .pubsub import broker

ROOM_NAME_MAX = 50
MESSAGE_MAX_LEN = 2000
HISTORY_LIMIT = 200
# 브라우저에서 바로 보여줘도 안전한 이미지 형식(SVG는 스크립트 위험 때문에 제외)
INLINE_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


# ---------- 멤버십 ----------

def get_membership(db: Session, room_id: int, user_id: int) -> ChatMember | None:
    return db.scalar(select(ChatMember).where(ChatMember.room_id == room_id, ChatMember.user_id == user_id))


def joined_members(db: Session, room_id: int) -> list[ChatMember]:
    return list(db.scalars(
        select(ChatMember)
        .where(ChatMember.room_id == room_id, ChatMember.status == "joined")
        .order_by(ChatMember.joined_at, ChatMember.id)
    ))


def invited_members(db: Session, room_id: int) -> list[ChatMember]:
    return list(db.scalars(
        select(ChatMember).where(ChatMember.room_id == room_id, ChatMember.status == "invited").order_by(ChatMember.id)
    ))


# ---------- 읽음 / 안 읽은 수 ----------

def max_message_id(db: Session, room_id: int) -> int:
    return db.scalar(select(func.max(ChatMessage.id)).where(ChatMessage.room_id == room_id)) or 0


def mark_read(db: Session, member: ChatMember) -> bool:
    """방의 최신 메시지까지 읽음 처리. 변경되면 True."""
    latest = max_message_id(db, member.room_id)
    if latest > member.last_read_message_id:
        member.last_read_message_id = latest
        return True
    return False


def _unread_condition(user_id: int):
    return and_(
        ChatMember.user_id == user_id,
        ChatMember.status == "joined",
        ChatMessage.room_id == ChatMember.room_id,
        ChatMessage.id > ChatMember.last_read_message_id,
        ChatMessage.kind != "system",
        or_(ChatMessage.user_id.is_(None), ChatMessage.user_id != user_id),
    )


def unread_by_room(db: Session, user_id: int) -> dict[int, int]:
    rows = db.execute(
        select(ChatMessage.room_id, func.count(ChatMessage.id))
        .join(ChatMember, ChatMember.room_id == ChatMessage.room_id)
        .where(_unread_condition(user_id))
        .group_by(ChatMessage.room_id)
    ).all()
    return dict(rows)


def unread_in_room(db: Session, room_id: int, user_id: int) -> int:
    return unread_by_room(db, user_id).get(room_id, 0)


def chat_badge_count(db: Session, user_id: int) -> int:
    """상단 메뉴 배지: 안 읽은 메시지 + 대기 중인 초대."""
    unread = sum(unread_by_room(db, user_id).values())
    invites = db.scalar(
        select(func.count(ChatMember.id)).where(ChatMember.user_id == user_id, ChatMember.status == "invited")
    ) or 0
    return unread + invites


def readers_map(members: list[ChatMember]) -> dict[int, int]:
    """user_id -> 마지막으로 읽은 메시지 id (입장한 멤버만)."""
    return {m.user_id: m.last_read_message_id for m in members}


def read_counts(messages: list[ChatMessage], readers: dict[int, int]) -> dict[int, int]:
    """메시지별 'N명 읽음': 보낸 사람을 제외하고 그 메시지까지 읽은 멤버 수."""
    return {
        m.id: sum(1 for uid, last in readers.items() if uid != m.user_id and last >= m.id)
        for m in messages
        if m.kind != "system"
    }


# ---------- 멘션 ----------

def find_mentions(content: str, members: list[ChatMember], sender_id: int) -> list[User]:
    """본문에서 @표시이름 으로 언급된 멤버를 찾습니다. 긴 이름부터 매칭해 '철수'와 '철수형'이 겹치지 않게 합니다."""
    text = content
    found: list[User] = []
    for m in sorted(members, key=lambda x: len(x.user.name), reverse=True):
        token = f"@{m.user.name}"
        if token in text:
            text = text.replace(token, " ")
            if m.user_id != sender_id:
                found.append(m.user)
    return found


def render_content(content: str | None, names: list[str]) -> Markup:
    """본문을 이스케이프하고 @멘션을 강조 표시합니다."""
    html = str(escape(content or ""))
    for name in sorted(set(names), key=len, reverse=True):
        token = str(escape(f"@{name}"))
        html = html.replace(token, f'<span class="mention">{token}</span>')
    return Markup(html)


# ---------- 첨부파일 ----------

def upload_root() -> Path:
    return Path(settings.upload_dir).resolve()


def guess_mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def is_inline_image(msg: ChatMessage) -> bool:
    return msg.kind == "file" and (msg.file_mime or "") in INLINE_IMAGE_TYPES


def save_upload(upload: UploadFile, room_id: int) -> tuple[str, int]:
    """첨부파일을 저장하고 (업로드 폴더 기준 상대경로, 크기)를 돌려줍니다. 최대 크기를 넘으면 지웁니다."""
    limit = settings.max_upload_mb * 1024 * 1024
    rel_path = f"chat/{room_id}/{uuid.uuid4().hex}"
    dest = upload_root() / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise AppError(f"파일은 최대 {settings.max_upload_mb}MB까지 올릴 수 있습니다.", 413)
                out.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise AppError("빈 파일은 올릴 수 없습니다.")
    return rel_path, size


def file_path_of(msg: ChatMessage) -> Path | None:
    if not msg.file_path:
        return None
    path = (upload_root() / msg.file_path).resolve()
    if upload_root() not in path.parents:  # 경로 조작 방지
        return None
    return path


def delete_room_files(room_id: int) -> None:
    shutil.rmtree(upload_root() / "chat" / str(room_id), ignore_errors=True)


def format_size(size: int | None) -> str:
    size = size or 0
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size}B"


templates.env.filters["filesize"] = format_size
templates.env.globals["is_inline_image"] = is_inline_image
templates.env.globals["render_content"] = render_content


# ---------- 렌더링 / 실시간 이벤트 ----------

def message_html(msg: ChatMessage, names: list[str], reads: dict[int, int], me_id: int | None = None) -> str:
    return templates.get_template("_chat_message.html").render(
        {"m": msg, "mention_names": names, "reads": reads, "me_id": me_id}
    )


def add_system_message(db: Session, room_id: int, text: str) -> ChatMessage:
    msg = ChatMessage(room_id=room_id, user_id=None, kind="system", content=text)
    db.add(msg)
    db.flush()
    return msg


def publish_message(db: Session, msg: ChatMessage) -> None:
    """방 구독자에게 새 메시지를, 멤버 개인 채널에는 안 읽은 수 갱신을 보냅니다. commit 이후 호출하세요."""
    members = joined_members(db, msg.room_id)
    names = [m.user.name for m in members]
    broker.publish(f"room:{msg.room_id}", {
        "type": "message",
        "id": msg.id,
        "user_id": msg.user_id,
        "html": message_html(msg, names, {msg.id: 0}),
    })
    if msg.kind == "system":
        return
    preview = msg.content or (f"📎 {msg.file_name}" if msg.file_name else "")
    for m in members:
        if m.user_id == msg.user_id:
            continue
        broker.publish(f"user:{m.user_id}", {
            "type": "unread",
            "room_id": msg.room_id,
            "count": unread_in_room(db, msg.room_id, m.user_id),
            "preview": preview[:60],
        })


def publish_read(member: ChatMember) -> None:
    broker.publish(f"room:{member.room_id}", {
        "type": "read",
        "user_id": member.user_id,
        "last_read": member.last_read_message_id,
    })


def publish_members(db: Session, room_id: int) -> None:
    broker.publish(f"room:{room_id}", {
        "type": "members",
        "readers": {str(k): v for k, v in readers_map(joined_members(db, room_id)).items()},
    })
