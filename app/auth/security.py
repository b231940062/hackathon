"""Нууц үгийн hash (Argon2id) ба CSRF хамгаалалт."""
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request

_hasher = PasswordHasher()  # Argon2id, давс (salt) автоматаар
# Бүртгэлгүй имэйлээр нэвтрэхэд ч мөн адил хугацаа зарцуулж, хэрэглэгч байгаа эсэхийг задруулахгүй
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


async def csrf_protect(request: Request) -> None:
    """Бүх POST хүсэлтэд CSRF токен шалгана (форм талбар эсвэл X-CSRF-Token толгой)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    expected = request.session.get("csrf")
    token = request.headers.get("X-CSRF-Token")
    if not token:
        form = await request.form()
        token = form.get("csrf_token")
    if not expected or not isinstance(token, str) or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="CSRF токен буруу байна. Хуудсаа дахин ачаална уу.")
