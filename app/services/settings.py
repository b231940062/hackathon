"""Админ самбараас удирдах платформын тохиргоо."""
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.models import Setting

DEFAULTS = {
    "site_announcement": "",
    "high_priority_threshold": "70",
    "high_support_threshold": "25",
    "duplicate_threshold": "0.55",
    "allow_registration": "1",
    "demo_mode": "1" if app_settings.demo_mode_default else "0",
}

LABELS = {
    "site_announcement": "Нүүр хуудасны зарлал",
    "high_priority_threshold": "Шуурхай анхаарах ач холбогдлын босго (0–100)",
    "high_support_threshold": "Гишүүнд мэдэгдэх дэмжлэгийн босго",
    "duplicate_threshold": "Давхардал илрүүлэх босго (0.3–0.95)",
    "allow_registration": "Шинэ иргэн бүртгүүлэхийг зөвшөөрөх",
    "demo_mode": "Демо горим (демо бүртгэл, дэмжлэг симуляци)",
}


def get_setting(db: Session, key: str) -> str:
    row = db.get(Setting, key)
    return row.value if row is not None else DEFAULTS.get(key, "")


def get_int(db: Session, key: str) -> int:
    try:
        return int(get_setting(db, key))
    except ValueError:
        return int(DEFAULTS[key])


def get_float(db: Session, key: str) -> float:
    try:
        return float(get_setting(db, key))
    except ValueError:
        return float(DEFAULTS[key])


def get_bool(db: Session, key: str) -> bool:
    return get_setting(db, key) == "1"


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
