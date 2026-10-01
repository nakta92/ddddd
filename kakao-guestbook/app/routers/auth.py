import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import kakao
from ..config import settings
from ..database import get_db
from ..deps import flash, get_current_user, render, safe_next
from ..models import User, utcnow

router = APIRouter()


def upsert_kakao_user(db: Session, profile: kakao.KakaoProfile) -> User:
    """카카오 프로필로 사용자를 생성하거나 닉네임/프로필 이미지를 최신으로 갱신합니다."""
    user = db.scalar(select(User).where(User.kakao_id == profile.id))
    if user is None:
        user = User(kakao_id=profile.id, created_at=utcnow())
        db.add(user)
    user.nickname = profile.nickname
    user.profile_image = profile.profile_image
    user.last_login_at = utcnow()
    db.commit()
    db.refresh(user)
    return user


@router.get("/login")
def login_page(request: Request, next: str = "/", db: Session = Depends(get_db),
               user: User | None = Depends(get_current_user)):
    if user:
        return RedirectResponse(safe_next(next), status_code=303)
    return render(request, "login.html", user, db, next=safe_next(next))


@router.get("/auth/kakao/login")
def kakao_login(request: Request, next: str = "/"):
    if not settings.kakao_enabled:
        flash(request, "카카오 REST API 키가 설정되지 않았습니다. .env의 KAKAO_REST_API_KEY를 확인하세요.", "error")
        return RedirectResponse("/login", status_code=303)
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    request.session["login_next"] = safe_next(next)
    return RedirectResponse(kakao.authorize_url(state), status_code=302)


@router.get("/auth/kakao/callback")
def kakao_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    db: Session = Depends(get_db),
):
    saved_state = request.session.pop("oauth_state", None)
    next_path = safe_next(request.session.pop("login_next", "/"))

    if error:
        flash(request, f"카카오 로그인이 취소되었거나 실패했습니다. ({error_description or error})", "error")
        return RedirectResponse("/login", status_code=303)
    if not code or not state or not saved_state or not secrets.compare_digest(state, saved_state):
        flash(request, "잘못된 로그인 요청입니다. 다시 시도해 주세요.", "error")
        return RedirectResponse("/login", status_code=303)

    try:
        token = kakao.exchange_token(code)
        profile = kakao.fetch_user(token)
    except kakao.KakaoError as e:
        flash(request, str(e), "error")
        return RedirectResponse("/login", status_code=303)

    user = upsert_kakao_user(db, profile)
    request.session["user_id"] = user.id
    flash(request, f"{user.name}님, 환영합니다!", "success")
    return RedirectResponse(next_path, status_code=303)


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    flash(request, "로그아웃되었습니다.")
    return RedirectResponse("/", status_code=303)
