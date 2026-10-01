"""알림 생성/조회 헬퍼. 호출한 쪽에서 commit 합니다."""

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import Notification, User, utcnow

# 알림 종류 -> 목록에 표시할 아이콘
NOTIFICATION_ICONS = {
    "comment": "💬",
    "reply": "↪️",
    "reaction": "👍",
    "friend_request": "🤝",
    "friend_accept": "🤝",
    "friend_reject": "🙅",
    "chat_invite": "💌",
    "mention": "📣",
}


def snippet(text: str, length: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= length else text[: length - 1] + "…"


def notify(db: Session, recipient_id: int, actor: User | None, type_: str, message: str,
           target_type: str | None = None, target_id: int | None = None, dedupe: bool = False) -> Notification | None:
    """알림을 추가합니다. 자기 자신에게는 보내지 않습니다.

    dedupe=True면 같은 사람·종류·대상의 안 읽은 알림이 있을 때 새로 만들지 않고 내용/시각만 갱신합니다
    (예: 반응을 여러 번 바꿔 누르는 경우 알림 폭주 방지).
    """
    if actor is not None and recipient_id == actor.id:
        return None
    if dedupe and actor is not None:
        existing = db.scalar(
            select(Notification).where(
                Notification.user_id == recipient_id,
                Notification.actor_id == actor.id,
                Notification.type == type_,
                Notification.target_type == target_type,
                Notification.target_id == target_id,
                Notification.is_read.is_(False),
            )
        )
        if existing:
            existing.message = message
            existing.created_at = utcnow()
            return existing
    n = Notification(
        user_id=recipient_id,
        actor_id=actor.id if actor else None,
        type=type_,
        message=message,
        target_type=target_type,
        target_id=target_id,
    )
    db.add(n)
    return n


def unread_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count(Notification.id)).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    ) or 0


def mark_all_read(db: Session, user_id: int) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
