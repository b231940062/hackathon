"""Цаг, огноо, форматлах жижиг туслах функцууд."""
from datetime import date, datetime, timedelta, timezone

LOCAL_OFFSET = timedelta(hours=8)  # Улаанбаатарын цаг (UTC+8)

AVATAR_COLORS = ["#1e63d6", "#0891b2", "#7c3aed", "#db2777", "#ea580c", "#16a34a",
                 "#ca8a04", "#0f766e", "#9333ea", "#dc2626", "#2563eb", "#65a30d"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_local(dt: datetime | None) -> datetime | None:
    return dt + LOCAL_OFFSET if dt else None


def local_today() -> date:
    return (utcnow() + LOCAL_OFFSET).date()


def timeago(dt: datetime | None) -> str:
    if not dt:
        return ""
    secs = (utcnow() - dt).total_seconds()
    if secs < 60:
        return "дөнгөж сая"
    mins = int(secs // 60)
    if mins < 60:
        return f"{mins} минутын өмнө"
    hours = mins // 60
    if hours < 24:
        return f"{hours} цагийн өмнө"
    days = hours // 24
    if days < 30:
        return f"{days} өдрийн өмнө"
    months = days // 30
    if months < 12:
        return f"{months} сарын өмнө"
    return f"{days // 365} жилийн өмнө"


def fmt_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        value = to_local(value)
    return value.strftime("%Y.%m.%d")


def fmt_datetime(value: datetime | None) -> str:
    if not value:
        return ""
    return to_local(value).strftime("%Y.%m.%d %H:%M")


def initials(name: str | None) -> str:
    if not name:
        return "?"
    tokens = [t for t in name.replace(".", " ").split() if t]
    if not tokens:
        return "?"
    given = max(tokens, key=len)
    others = [t for t in tokens if t is not given]
    return (given[:1] + (others[0][:1] if others else "")).upper()


def avatar_color(seed: str | None) -> str:
    seed = seed or "?"
    return AVATAR_COLORS[sum(ord(c) for c in seed) % len(AVATAR_COLORS)]


def safe_next(url: str | None, default: str) -> str:
    """Нээлттэй redirect-ээс сэргийлж, зөвхөн дотоод замыг зөвшөөрнө."""
    if url and url.startswith("/") and not url.startswith("//") and "\\" not in url:
        return url
    return default


def parse_int(value, default=None):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default
