from fastapi import Request
from sqlalchemy import create_engine, event, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_on_connect(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()
        # SQLite-ийн lower() зөвхөн ASCII дээр ажилладаг тул кирилл хайлтад Python-ий lower ашиглана
        dbapi_conn.create_function("unicode_lower", 1, lambda s: s.lower() if isinstance(s, str) else s,
                                   deterministic=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def ci_contains(column, needle: str):
    """Том жижиг үсэг ялгахгүй хайлт (кирилл дэмжинэ). Параметрчилсэн тул SQL injection-ээс хамгаалагдсан."""
    needle = needle.lower()
    if _is_sqlite:
        return func.unicode_lower(column).contains(needle, autoescape=True)
    return func.lower(column).contains(needle, autoescape=True)


def get_db(request: Request):
    db = SessionLocal()
    request.state.db = db
    try:
        yield db
    finally:
        db.close()
