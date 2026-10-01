import math

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import AppError, flash, login_required, render, wants_json
from ..chat import get_membership
from ..models import ChatMessage, Comment, Friendship, Notification, Post, User
from ..notify import NOTIFICATION_ICONS, mark_all_read, unread_count
from ..views import post_url

router = APIRouter(prefix="/notifications")

PER_PAGE = 20


def target_url(db: Session, n: Notification) -> str | None:
    """알림 대상의 현재 위치(URL). 대상이 삭제됐으면 None."""
    if n.target_type == "post":
        if db.get(Post, n.target_id):
            return post_url(db, n.target_id, f"post-{n.target_id}")
    elif n.target_type == "comment":
        comment = db.get(Comment, n.target_id)
        if comment:
            return post_url(db, comment.post_id, f"comment-{comment.id}")
    elif n.target_type == "friends":
        # 거절 등으로 관계 행이 없어도 친구 페이지로 이동
        if n.target_id and db.get(Friendship, n.target_id):
            return f"/friends?highlight=fr-{n.target_id}#fr-{n.target_id}"
        return "/friends"
    elif n.target_type == "chat_room":
        member = get_membership(db, n.target_id, n.user_id)
        if member and member.status == "invited":
            return f"/chat?highlight=invite-{n.target_id}#invite-{n.target_id}"
        if member and member.status == "joined":
            return f"/chat/{n.target_id}"
    elif n.target_type == "chat_message":
        msg = db.get(ChatMessage, n.target_id)
        member = get_membership(db, msg.room_id, n.user_id) if msg else None
        if member and member.status == "joined":
            return f"/chat/{msg.room_id}?highlight=msg-{msg.id}#msg-{msg.id}"
    return None


@router.get("")
def notification_list(request: Request, page: int = 1, db: Session = Depends(get_db),
                      user: User = Depends(login_required)):
    total = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id)) or 0
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(max(1, page), pages)
    items = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
        .offset((page - 1) * PER_PAGE)
        .limit(PER_PAGE)
    ).all()
    return render(request, "notifications.html", user, db, items=items, page=page, pages=pages,
                  total=total, icons=NOTIFICATION_ICONS)


@router.get("/unread-count")
def notification_unread_count(db: Session = Depends(get_db), user: User = Depends(login_required)):
    return {"count": unread_count(db, user.id)}


@router.get("/{notification_id}/go")
def notification_go(request: Request, notification_id: int, db: Session = Depends(get_db),
                    user: User = Depends(login_required)):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise AppError("알림을 찾을 수 없습니다.", 404, redirect_to="/notifications")
    n.is_read = True
    db.commit()
    url = target_url(db, n)
    if url is None:
        flash(request, "삭제되었거나 더 이상 볼 수 없는 대상입니다.", "error")
        return RedirectResponse("/notifications", status_code=303)
    return RedirectResponse(url, status_code=303)


@router.post("/read-all")
def notification_read_all(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    mark_all_read(db, user.id)
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True, "reload": True})
    return RedirectResponse("/notifications", status_code=303)
