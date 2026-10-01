from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import AppError, flash, get_current_user, login_required, render, wants_json
from ..models import Comment, Post, User

router = APIRouter()

DISPLAY_NAME_MAX = 30
BIO_MAX = 300


def user_stats(db: Session, user_id: int) -> dict:
    return {
        "posts": db.scalar(select(func.count(Post.id)).where(Post.user_id == user_id)) or 0,
        "comments": db.scalar(select(func.count(Comment.id)).where(Comment.user_id == user_id)) or 0,
    }


@router.get("/me")
def my_info(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    return render(request, "me.html", user, db, stats=user_stats(db, user.id))


@router.post("/me")
def update_my_info(request: Request, display_name: str = Form(""), bio: str = Form(""),
                   db: Session = Depends(get_db), user: User = Depends(login_required)):
    display_name = " ".join(display_name.split())  # 앞뒤/중복 공백 정리
    bio = bio.strip()
    if len(display_name) > DISPLAY_NAME_MAX:
        raise AppError(f"표시 이름은 {DISPLAY_NAME_MAX}자 이하로 입력해 주세요.", redirect_to="/me")
    if "@" in display_name:
        raise AppError("표시 이름에는 @를 사용할 수 없습니다.", redirect_to="/me")
    if len(bio) > BIO_MAX:
        raise AppError(f"자기소개는 {BIO_MAX}자 이하로 입력해 주세요.", redirect_to="/me")
    user.display_name = display_name or None  # 비우면 카카오 닉네임으로 표시
    user.bio = bio or None
    db.commit()
    if wants_json(request):
        return JSONResponse({"ok": True, "message": "내 정보를 저장했습니다.", "reload": True})
    flash(request, "내 정보를 저장했습니다.", "success")
    return RedirectResponse("/me", status_code=303)


@router.get("/users/{user_id}")
def user_profile(request: Request, user_id: int, db: Session = Depends(get_db),
                 user: User | None = Depends(get_current_user)):
    target = db.get(User, user_id)
    if target is None:
        raise AppError("사용자를 찾을 수 없습니다.", 404, redirect_to="/")
    return render(request, "user.html", user, db, target=target, stats=user_stats(db, target.id))
