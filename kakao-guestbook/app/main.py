import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import engine
from .deps import BASE_DIR, AppError, LoginRequired, back_path, flash, login_url, wants_json
from .migrations import init_db
from .routers import admin, auth, chat, friends, guestbook, notifications, profile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")
DEFAULT_SECRET = "change-me-in-production"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 새 테이블 생성 + 기존 DB에 누락된 컬럼 자동 추가
    init_db(engine)
    if settings.secret_key in (DEFAULT_SECRET, "change-me-to-a-long-random-string"):
        logger.warning("SECRET_KEY가 기본값입니다. 운영 환경에서는 반드시 .env에서 긴 임의 문자열로 바꾸세요.")
    if not settings.kakao_enabled:
        logger.warning("KAKAO_REST_API_KEY가 비어 있어 카카오 로그인을 사용할 수 없습니다.")
    yield


class BodySizeLimitMiddleware:
    """Content-Length가 한도를 넘는 요청은 본문을 받기 전에 413으로 거절합니다(대용량 업로드 방지)."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            length = dict(scope["headers"]).get(b"content-length")
            if length and length.isdigit() and int(length) > self.max_bytes:
                message = f"요청이 너무 큽니다. 파일은 최대 {settings.max_upload_mb}MB까지 올릴 수 있습니다."
                await JSONResponse({"ok": False, "error": message}, 413)(scope, receive, send)
                return
        await self.app(scope, receive, send)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
# 파일 한도 + 폼 필드 여유분 1MB
app.add_middleware(BodySizeLimitMiddleware, max_bytes=(settings.max_upload_mb + 1) * 1024 * 1024)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="guestbook_session",
    max_age=60 * 60 * 24 * 14,
    same_site="lax",
    https_only=settings.session_https_only,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(auth.router)
app.include_router(guestbook.router)
app.include_router(profile.router)
app.include_router(admin.router)
app.include_router(notifications.router)
app.include_router(friends.router)
app.include_router(chat.router)


@app.get("/health", include_in_schema=False)
def health():
    """컨테이너 헬스체크: DB 연결까지 확인합니다."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover - DB 장애 시
        return JSONResponse({"status": "error", "detail": str(e)}, 503)
    return {"status": "ok"}


@app.exception_handler(LoginRequired)
async def handle_login_required(request: Request, _exc: LoginRequired):
    if request.method == "GET":
        next_path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    else:
        next_path = back_path(request)
    if wants_json(request):
        return JSONResponse({"ok": False, "error": "로그인이 필요합니다.", "login": login_url(next_path)}, 401)
    flash(request, "로그인이 필요합니다.", "error")
    return RedirectResponse(login_url(next_path), status_code=303)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    if wants_json(request):
        return JSONResponse({"ok": False, "error": exc.message}, exc.status_code)
    flash(request, exc.message, "error")
    return RedirectResponse(exc.redirect_to or back_path(request), status_code=303)
