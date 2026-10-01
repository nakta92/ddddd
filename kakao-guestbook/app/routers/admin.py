import math

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import AppError, admin_required, flash, render, templates, wants_json
from ..models import Post, User

router = APIRouter(prefix="/admin")

USERS_PER_PAGE = 20


def post_counts(db: Session, user_ids: list[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = db.execute(
        select(Post.user_id, func.count(Post.id)).where(Post.user_id.in_(user_ids)).group_by(Post.user_id)
    ).all()
    return dict(rows)


def row_response(request: Request, db: Session, admin: User, target: User, message: str):
    if wants_json(request):
        html = templates.get_template("_admin_row.html").render(
            {"request": request, "user": admin, "u": target, "post_counts": post_counts(db, [target.id])}
        )
        return JSONResponse({"ok": True, "message": message, "replace": [{"id": f"user-row-{target.id}", "html": html}]})
    flash(request, message, "success")
    return RedirectResponse("/admin", status_code=303)


def get_target(db: Session, user_id: int) -> User:
    target = db.get(User, user_id)
    if target is None:
        raise AppError("회원을 찾을 수 없습니다.", 404, redirect_to="/admin")
    return target


@router.get("")
def admin_home(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db),
               admin: User = Depends(admin_required)):
    stmt = select(User)
    count_stmt = select(func.count(User.id))
    q = q.strip()
    if q:
        like = f"%{q}%"
        cond = or_(User.nickname.ilike(like), User.display_name.ilike(like), User.username.ilike(like))
        stmt, count_stmt = stmt.where(cond), count_stmt.where(cond)
    total = db.scalar(count_stmt) or 0
    pages = max(1, math.ceil(total / USERS_PER_PAGE))
    page = min(max(1, page), pages)
    users = db.scalars(stmt.order_by(User.id.desc()).offset((page - 1) * USERS_PER_PAGE).limit(USERS_PER_PAGE)).all()
    return render(
        request, "admin.html", admin, db,
        users=users, q=q, page=page, pages=pages, total=total,
        post_counts=post_counts(db, [u.id for u in users]),
        admin_count=db.scalar(select(func.count(User.id)).where(User.is_admin.is_(True))) or 0,
    )


@router.post("/users/{user_id}/grant")
def grant_admin(request: Request, user_id: int, db: Session = Depends(get_db),
                admin: User = Depends(admin_required)):
    target = get_target(db, user_id)
    target.is_admin = True
    db.commit()
    return row_response(request, db, admin, target, f"{target.name}님에게 관리자 권한을 부여했습니다.")


@router.post("/users/{user_id}/revoke")
def revoke_admin(request: Request, user_id: int, db: Session = Depends(get_db),
                 admin: User = Depends(admin_required)):
    target = get_target(db, user_id)
    if target.id == admin.id:
        raise AppError("본인의 관리자 권한은 해제할 수 없습니다.", 400, redirect_to="/admin")
    target.is_admin = False
    db.commit()
    return row_response(request, db, admin, target, f"{target.name}님의 관리자 권한을 해제했습니다.")


@router.post("/users/{user_id}/delete")
def delete_user(request: Request, user_id: int, db: Session = Depends(get_db),
                admin: User = Depends(admin_required)):
    target = get_target(db, user_id)
    if target.id == admin.id:
        raise AppError("본인 계정은 삭제할 수 없습니다.", 400, redirect_to="/admin")
    name = target.name
    db.delete(target)  # 글·댓글·반응 등은 ON DELETE CASCADE로 함께 삭제
    db.commit()
    message = f"{name}님을 삭제했습니다."
    if wants_json(request):
        return JSONResponse({"ok": True, "message": message, "removed": f"user-row-{user_id}"})
    flash(request, message, "success")
    return RedirectResponse("/admin", status_code=303)
