"""친구(사이 맺기) 관계 조회 헬퍼."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .models import Friendship

PRESET_LABELS = ("친구", "동료")
LABEL_MAX = 20


def friendship_between(db: Session, a_id: int, b_id: int) -> Friendship | None:
    return db.scalar(
        select(Friendship).where(
            or_(
                and_(Friendship.requester_id == a_id, Friendship.addressee_id == b_id),
                and_(Friendship.requester_id == b_id, Friendship.addressee_id == a_id),
            )
        )
    )


def are_friends(db: Session, a_id: int, b_id: int) -> bool:
    f = friendship_between(db, a_id, b_id)
    return f is not None and f.status == "accepted"


def my_friendships(db: Session, me_id: int) -> list[Friendship]:
    return list(
        db.scalars(
            select(Friendship)
            .where(or_(Friendship.requester_id == me_id, Friendship.addressee_id == me_id))
            .order_by(Friendship.id.desc())
        )
    )


def friend_ids(db: Session, me_id: int) -> set[int]:
    return {
        f.addressee_id if f.requester_id == me_id else f.requester_id
        for f in my_friendships(db, me_id)
        if f.status == "accepted"
    }


def relation_map(db: Session, me_id: int | None) -> dict[int, dict]:
    """상대 사용자 id -> {status: friend|sent|received, label, fid}. 화면에 관계 표시용."""
    if me_id is None:
        return {}
    result = {}
    for f in my_friendships(db, me_id):
        other_id = f.addressee_id if f.requester_id == me_id else f.requester_id
        if f.status == "accepted":
            status = "friend"
        else:
            status = "sent" if f.requester_id == me_id else "received"
        result[other_id] = {"status": status, "label": f.label_for(me_id), "fid": f.id}
    return result


def clean_label(choice: str, custom: str = "") -> str | None:
    """프리셋(친구/동료) 또는 직접 입력 라벨. 잘못된 값이면 None."""
    choice = (choice or "").strip()
    if choice in PRESET_LABELS:
        return choice
    raw = custom if choice == "custom" else choice
    label = " ".join((raw or "").split())
    if not label or len(label) > LABEL_MAX:
        return None
    return label
