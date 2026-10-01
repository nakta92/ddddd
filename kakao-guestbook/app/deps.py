"""라우터 공통 의존성: 템플릿, 현재 사용자, 플래시 메시지, AJAX 판별."""

from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import REACTIONS, User
from .timeutil import format_kst

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.filters["kst"] = format_kst
templates.env.globals["settings"] = settings
templates.env.globals["REACTIONS"] = REACTIONS
# 정적 파일 캐시 무효화용 버전(CSS/JS 변경 시 올립니다)
templates.env.globals["ASSET_VERSION"] = "6.0"


class LoginRequired(Exception):
    """로그인이 필요한 요청. main.py의 핸들러가 401(JSON) 또는 로그인 페이지 리다이렉트로 바꿉니다."""


class AppError(Exception):
    """사용자에게 보여줄 오류. AJAX면 JSON, 아니면 플래시 + 리다이렉트로 응답합니다."""

    def __init__(self, message: str, status_code: int = 400, redirect_to: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.redirect_to = redirect_to


def wants_json(request: Request) -> bool:
    return (
        request.headers.get("x-requested-with") == "fetch"
        or "application/json" in request.headers.get("accept", "")
    )


def flash(request: Request, message: str, category: str = "info") -> None:
    # 세션은 키 재대입으로만 변경이 감지되므로 리스트를 새로 만들어 대입합니다.
    request.session["_flashes"] = [*request.session.get("_flashes", []), {"message": message, "category": category}]


def pop_flashes(request: Request) -> list[dict]:
    return request.session.pop("_flashes", [])


def safe_next(target: str | None, default: str = "/") -> str:
    """오픈 리다이렉트 방지: 같은 사이트 내부 경로만 허용."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return default
    return target


def back_path(request: Request, default: str = "/") -> str:
    """같은 사이트의 Referer 경로(없으면 default). JS 미사용 폼 제출 후 원래 화면으로 돌아갈 때 씁니다."""
    referer = request.headers.get("referer")
    if referer:
        ref = urlparse(referer)
        if ref.netloc == request.url.netloc:
            return safe_next(ref.path + (f"?{ref.query}" if ref.query else ""), default)
    return default


def login_url(next_path: str = "/") -> str:
    return f"/login?next={quote(safe_next(next_path), safe='/')}"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None:  # 탈퇴/삭제된 사용자의 세션 정리
        request.session.pop("user_id", None)
    return user


def login_required(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def admin_required(user: User = Depends(login_required)) -> User:
    if not user.is_admin:
        raise AppError("관리자만 접근할 수 있습니다.", 403, redirect_to="/")
    return user


def base_context(request: Request, user: User | None, db: Session) -> dict:
    from .chat import chat_badge_count
    from .friends import pending_friend_requests
    from .notify import unread_count

    return {
        "user": user,
        "flashes": pop_flashes(request),
        "unread_notifications": unread_count(db, user.id) if user else 0,
        "chat_badge": chat_badge_count(db, user.id) if user else 0,
        "friend_requests": pending_friend_requests(db, user.id) if user else 0,
    }


def render(request: Request, name: str, user: User | None, db: Session, status_code: int = 200, **ctx):
    context = base_context(request, user, db)
    context.update(ctx)
    return templates.TemplateResponse(request, name, context, status_code=status_code)
