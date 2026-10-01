import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import engine
from .deps import BASE_DIR, AppError, LoginRequired, back_path, flash, login_url, wants_json
from .migrations import init_db
from .routers import admin, auth, guestbook, notifications, profile

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 새 테이블 생성 + 기존 DB에 누락된 컬럼 자동 추가
    init_db(engine)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
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
