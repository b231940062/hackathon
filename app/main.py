"""Холбоос — иргэд ба УИХ-ын гишүдийг холбох асуудал мэдээлэх, хянах платформ."""
import logging
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

import app.models  # noqa: F401  (бүх хүснэгтийг metadata-д бүртгэнэ)
from app.auth.deps import Forbidden, LoginRequired, get_current_user
from app.auth.security import csrf_protect
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import User
from app.routers import admin, auth, citizen, issues, mp, public
from app.seed import ensure_demo_images, seed_if_empty
from app.services.issues import recompute_all_priorities
from app.templating import flash, render

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")
log = logging.getLogger("holboos")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    seed_if_empty()
    ensure_demo_images()
    with SessionLocal() as db:
        recompute_all_priorities(db)  # хугацааны оноо өдөр бүр өөрчлөгддөг
    log.info("Холбоос бэлэн боллоо → http://127.0.0.1:8000")
    yield


app = FastAPI(
    title="Холбоос",
    lifespan=lifespan,
    docs_url=None, redoc_url=None, openapi_url=None,
    # Хүсэлт бүрт: хэрэглэгчийг ачаалж, POST хүсэлтийн CSRF токеныг шалгана
    dependencies=[Depends(get_current_user), Depends(csrf_protect)],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response


app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="holboos_session",
                   max_age=60 * 60 * 24 * 7, same_site="lax", https_only=settings.session_https_only)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

for r in (public.router, auth.router, issues.router, citizen.router, mp.router, admin.router):
    app.include_router(r)


# ---------- Алдааны хуудсууд ----------
def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "") or request.url.path.startswith("/api/")


def _error_page(request: Request, status: int, title: str, message: str):
    with SessionLocal() as db:
        uid = request.session.get("uid") if "session" in request.scope else None
        user = db.get(User, uid) if uid else None
        request.state.user = user
        return render(request, "errors/error.html", {"code": status, "title": title, "message": message},
                      status_code=status, db=db, user=user)


@app.exception_handler(LoginRequired)
async def on_login_required(request: Request, _exc: LoginRequired):
    if _wants_json(request):
        return JSONResponse({"error": "Энэ үйлдлийг хийхийн тулд нэвтэрнэ үү.", "login": "/login"}, status_code=401)
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    if request.method != "GET":
        target = "/"
    flash(request, "Үргэлжлүүлэхийн тулд нэвтэрнэ үү.", "info")
    return RedirectResponse(f"/login?next={quote(target)}", status_code=303)


@app.exception_handler(Forbidden)
async def on_forbidden(request: Request, exc: Forbidden):
    if _wants_json(request):
        return JSONResponse({"error": exc.message}, status_code=403)
    return _error_page(request, 403, "Хандах эрхгүй", exc.message)


@app.exception_handler(StarletteHTTPException)
async def on_http_error(request: Request, exc: StarletteHTTPException):
    if _wants_json(request):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    if exc.status_code == 404:
        return _error_page(request, 404, "Хуудас олдсонгүй", "Таны хайсан хуудас устгагдсан эсвэл байхгүй байна.")
    if exc.status_code == 403:
        return _error_page(request, 403, "Хандах эрхгүй", str(exc.detail))
    return _error_page(request, exc.status_code, "Алдаа гарлаа", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, _exc: RequestValidationError):
    if _wants_json(request):
        return JSONResponse({"error": "Хүсэлтийн өгөгдөл буруу байна."}, status_code=400)
    return _error_page(request, 400, "Хүсэлт буруу байна", "Илгээсэн мэдээлэл буруу форматтай байна.")


@app.exception_handler(Exception)
async def on_server_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path, exc_info=exc)
    if _wants_json(request):
        return JSONResponse({"error": "Серверийн алдаа гарлаа."}, status_code=500)
    return _error_page(request, 500, "Серверийн алдаа", "Уучлаарай, түр алдаа гарлаа. Дахин оролдоно уу.")
