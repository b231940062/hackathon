"""Нэвтрэлт ба эрхийн шалгалтын dependency-үүд (role-based access control)."""
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


class LoginRequired(Exception):
    pass


class Forbidden(Exception):
    def __init__(self, message: str = "Танд энэ хуудсыг үзэх эрх байхгүй.") -> None:
        self.message = message


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    user = None
    if uid is not None:
        user = db.get(User, uid)
        if user is None or not user.is_active:
            request.session.pop("uid", None)
            user = None
    request.state.user = user
    return user


def login_required(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def require_roles(*roles: str):
    def _dep(user: User = Depends(login_required)) -> User:
        if user.role not in roles:
            raise Forbidden()
        return user
    return _dep


require_citizen = require_roles("citizen")
require_mp = require_roles("mp")
require_admin = require_roles("admin")


def role_home(user: User | None) -> str:
    if user is None:
        return "/"
    return {"admin": "/admin", "mp": "/mp"}.get(user.role, "/issues")
