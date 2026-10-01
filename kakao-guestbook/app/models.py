from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    """DB에는 항상 tz 정보 없는 UTC 시각으로 저장합니다. 표시는 KST로 변환합니다."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# 반응 종류: 키 -> (이모지, 라벨). 순서대로 화면에 표시됩니다.
REACTIONS: dict[str, tuple[str, str]] = {
    "like": ("👍", "좋아요"),
    "dislike": ("👎", "싫어요"),
    "thanks": ("🙏", "감사해요"),
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    kakao_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    # 카카오 없이 로그인하는 기본 관리자 계정 식별용(.env의 ADMIN_USERNAME)
    username: Mapped[str | None] = mapped_column(String(50), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(100), default="")
    profile_image: Mapped[str | None] = mapped_column(String(500))
    display_name: Mapped[str | None] = mapped_column(String(30))
    bio: Mapped[str | None] = mapped_column(String(300))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    @property
    def name(self) -> str:
        """화면 표시용 이름: 내 정보에서 정한 표시 이름 > 카카오 닉네임."""
        return self.display_name or self.nickname or "이름 없음"

    @property
    def login_type(self) -> str:
        return "카카오" if self.kakao_id else "관리자 계정"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    author: Mapped[User] = relationship(lazy="joined")


class Comment(Base):
    """댓글. parent_id가 있으면 대댓글이며, 대댓글은 1단계까지만 허용합니다."""

    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    author: Mapped[User] = relationship(lazy="joined")


class Reaction(Base):
    """글·댓글·대댓글 공용 반응. 대상(post_id / comment_id) 중 정확히 하나만 채웁니다."""

    __tablename__ = "reactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    post_id: Mapped[int | None] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    comment_id: Mapped[int | None] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    user: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("(post_id IS NULL) <> (comment_id IS NULL)", name="ck_reaction_one_target"),
        # 사용자당 대상별 반응 1개
        Index(
            "uq_reaction_user_post",
            "user_id",
            "post_id",
            unique=True,
            sqlite_where=text("post_id IS NOT NULL"),
        ),
        Index(
            "uq_reaction_user_comment",
            "user_id",
            "comment_id",
            unique=True,
            sqlite_where=text("comment_id IS NOT NULL"),
        ),
    )


class Notification(Base):
    """인앱 알림. 대상(target_type/target_id)은 클릭 시점에 위치를 계산해 이동합니다."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(String(300))
    # post | comment | friends | chat_room | chat_message
    target_type: Mapped[str | None] = mapped_column(String(20))
    target_id: Mapped[int | None] = mapped_column()
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id], lazy="joined")


class Friendship(Base):
    """사이 맺기. 요청자→수신자 단방향 행 하나로 관계를 표현하고, 관계 라벨은 각자 따로 붙입니다."""

    __tablename__ = "friendships"

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    addressee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | accepted
    requester_label: Mapped[str] = mapped_column(String(20), default="친구")
    addressee_label: Mapped[str] = mapped_column(String(20), default="친구")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)

    requester: Mapped[User] = relationship(foreign_keys=[requester_id], lazy="joined")
    addressee: Mapped[User] = relationship(foreign_keys=[addressee_id], lazy="joined")

    __table_args__ = (Index("uq_friendship_pair", "requester_id", "addressee_id", unique=True),)

    def other(self, me_id: int) -> User:
        return self.addressee if self.requester_id == me_id else self.requester

    def label_for(self, me_id: int) -> str:
        return self.requester_label if self.requester_id == me_id else self.addressee_label
