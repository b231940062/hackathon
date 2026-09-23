"""Тохиргоо: бүх нууц/орчны утгыг .env эсвэл орчны хувьсагчаас уншина."""
import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"

load_dotenv(BASE_DIR / ".env")
log = logging.getLogger("holboos")


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{(BASE_DIR / 'holboos.db').as_posix()}"
    # Render/Heroku "postgres://..." хэлбэрийг SQLAlchemy + psycopg 3 драйвер руу хөрвүүлнэ
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    # "sqlite:///./x.db" мэт харьцангуй замыг төслийн хавтастай холбоно (cwd-ээс хамаарахгүй)
    if url.startswith("sqlite:///./"):
        return f"sqlite:///{(BASE_DIR / url[len('sqlite:///./'):]).as_posix()}"
    return url


class Settings:
    def __init__(self) -> None:
        self.app_name = "Холбоос"
        self.secret_key = os.getenv("SECRET_KEY", "").strip()
        if not self.secret_key or self.secret_key.startswith("change-me"):
            self.secret_key = secrets.token_urlsafe(48)
            log.warning("SECRET_KEY тохируулаагүй тул түр түлхүүр үүсгэлээ. "
                        "Сервер дахин асахад сессүүд цуцлагдана. .env файлд SECRET_KEY оруулна уу.")
        self.database_url = _database_url()
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "5"))
        self.demo_password = os.getenv("DEMO_PASSWORD", "Holboos2026!")
        self.demo_mode_default = _bool("DEMO_MODE", True)
        self.session_https_only = _bool("SESSION_HTTPS_ONLY", False)
        self.static_dir = APP_DIR / "static"
        self.upload_dir = self.static_dir / "uploads"
        self.templates_dir = APP_DIR / "templates"
        self.demo_images_dir = BASE_DIR / "demo_images"


settings = Settings()
