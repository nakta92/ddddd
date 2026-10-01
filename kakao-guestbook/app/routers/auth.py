import secrets
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Form, Request
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
    if profile.id in settings.admin_kakao_id_set:  # .env의 ADMIN_KAKAO_IDS = 최초 관리자
        user.is_admin = True
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


# ---------- 기본 관리자 계정 로그인(카카오 없이) ----------

ADMIN_MAX_FAILURES = 5
ADMIN_LOCK_SECONDS = 300
_admin_failures: dict[str, deque] = defaultdict(deque)


def reset_admin_throttle() -> None:
    _admin_failures.clear()


def _admin_locked(key: str) -> bool:
    failures = _admin_failures[key]
    now = time.monotonic()
    while failures and now - failures[0] > ADMIN_LOCK_SECONDS:
        failures.popleft()
    return len(failures) >= ADMIN_MAX_FAILURES


@router.get("/auth/admin/login")
def admin_login_page(request: Request, db: Session = Depends(get_db),
                     user: User | None = Depends(get_current_user)):
    return render(request, "admin_login.html", user, db)


@router.post("/auth/admin/login")
def admin_login(request: Request, username: str = Form(""), password: str = Form(""),
                db: Session = Depends(get_db)):
    if not settings.admin_login_enabled:
        flash(request, "기본 관리자 계정이 설정되지 않았습니다. .env의 ADMIN_USERNAME/ADMIN_PASSWORD를 확인하세요.", "error")
        return RedirectResponse("/auth/admin/login", status_code=303)

    key = request.client.host if request.client else "unknown"
    if _admin_locked(key):
        flash(request, "로그인 실패가 너무 많습니다. 5분 후 다시 시도해 주세요.", "error")
        return RedirectResponse("/auth/admin/login", status_code=303)

    ok_user = secrets.compare_digest(username.encode(), settings.admin_username.encode())
    ok_pass = secrets.compare_digest(password.encode(), settings.admin_password.encode())
    if not (ok_user and ok_pass):
        _admin_failures[key].append(time.monotonic())
        flash(request, "아이디 또는 비밀번호가 올바르지 않습니다.", "error")
        return RedirectResponse("/auth/admin/login", status_code=303)

    _admin_failures.pop(key, None)
    user = db.scalar(select(User).where(User.username == settings.admin_username))
    if user is None:
        user = User(username=settings.admin_username, nickname="관리자", created_at=utcnow())
        db.add(user)
    user.is_admin = True
    user.last_login_at = utcnow()
    db.commit()
    request.session["user_id"] = user.id
    flash(request, "관리자 계정으로 로그인했습니다.", "success")
    return RedirectResponse("/admin", status_code=303)


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    flash(request, "로그아웃되었습니다.")
    return RedirectResponse("/", status_code=303)
