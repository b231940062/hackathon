from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils import utcnow

NOTIFICATION_ICONS = {
    "support": "👍",
    "comment": "💬",
    "received": "📥",
    "status": "🔄",
    "response": "🏛️",
    "resolved": "✅",
    "high_priority": "🔥",
    "high_support": "📈",
    "dispute": "⚠️",
    "system": "🔔",
}


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="system")
    message: Mapped[str] = mapped_column(String(300))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user = relationship("User", back_populates="notifications")
    issue = relationship("Issue", back_populates="notifications")

    @property
    def icon(self) -> str:
        return NOTIFICATION_ICONS.get(self.kind, "🔔")


class Setting(Base):
    """Админ самбараас өөрчлөх боломжтой платформын тохиргоо (key/value)."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(1000), default="")
