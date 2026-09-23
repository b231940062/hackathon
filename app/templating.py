"""Jinja2 орчин, render туслах функц, flash мессеж."""
import json
from urllib.parse import urlencode

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from sqlalchemy import func, select

from app.auth.security import get_csrf_token
from app.config import settings
from app.constants import (CATEGORIES, ORGANIZATIONS, ROLES, SCOPES, STATUS_INFO, STATUSES, URGENCY)
from app.models import Notification
from app.services import settings as cfg
from app.services.charts import SERIES as SERIES_COLORS
from app.services.priority import priority_level
from app.utils import avatar_color, fmt_date, fmt_datetime, initials, local_today, timeago

templates = Jinja2Templates(directory=str(settings.templates_dir))
env = templates.env
env.globals.update(
    STATUSES=STATUSES, STATUS_INFO=STATUS_INFO, CATEGORIES=CATEGORIES, URGENCY=URGENCY, SCOPES=SCOPES,
    ROLES=ROLES, ORGANIZATIONS=ORGANIZATIONS, priority_level=priority_level, today=local_today,
    MAX_UPLOAD_MB=settings.max_upload_mb, SERIES_COLORS=SERIES_COLORS,
)
env.filters.update(timeago=timeago, date=fmt_date, datetime=fmt_datetime, initials=initials,
                   avatar_color=avatar_color)


def url_with(request: Request, **params) -> str:
    """Одоогийн URL-ийн query параметрүүдийг хадгалж, заасныг солино (хуудаслалтад)."""
    query = dict(request.query_params)
    query.update({k: v for k, v in params.items()})
    return request.url.path + "?" + urlencode({k: v for k, v in query.items() if v not in ("", None)})


env.globals["url_with"] = url_with


def _tojson_safe(value) -> Markup:
    """<script> дотор аюулгүй JSON (</script> гэх мэтийг escape хийнэ)."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    text = (text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("'", "\\u0027"))
    return Markup(text)


env.filters["jsonscript"] = _tojson_safe


def flash(request: Request, message: str, category: str = "success") -> None:
    flashes = request.session.get("_flashes", [])
    flashes.append([category, message])
    request.session["_flashes"] = flashes[-5:]


def pop_flashes(request: Request) -> list:
    return request.session.pop("_flashes", [])


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200, db=None, user=None):
    db = db if db is not None else getattr(request.state, "db", None)
    user = user if user is not None else getattr(request.state, "user", None)
    unread = 0
    announcement = ""
    demo_mode = False
    if db is not None:
        if user is not None:
            unread = db.scalar(select(func.count()).select_from(Notification).where(
                Notification.user_id == user.id, Notification.is_read.is_(False))) or 0
        announcement = cfg.get_setting(db, "site_announcement")
        demo_mode = cfg.get_bool(db, "demo_mode")
    ctx = {
        "current_user": user,
        "csrf_token": get_csrf_token(request),
        "unread_count": unread,
        "flashes": pop_flashes(request),
        "announcement": announcement,
        "demo_mode": demo_mode,
        "path": request.url.path,
    }
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
