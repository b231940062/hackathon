from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import ROLES
from app.database import Base
from app.utils import avatar_color, initials, utcnow

# Гишүүнд оноогдсон хороод (олон-олон холбоос)
mp_khoroos = Table(
    "mp_khoroos",
    Base.metadata,
    Column("mp_profile_id", ForeignKey("mp_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("khoroo_id", ForeignKey("khoroos.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="citizen", index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"), nullable=True)
    khoroo_id: Mapped[int | None] = mapped_column(ForeignKey("khoroos.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    district = relationship("District")
    khoroo = relationship("Khoroo")
    mp_profile: Mapped["MPProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    issues = relationship("Issue", back_populates="author", foreign_keys="Issue.author_id", passive_deletes=True)
    comments = relationship("Comment", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    supports = relationship("Support", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan",
                                 passive_deletes=True)
    confirmations = relationship("ResolutionConfirmation", back_populates="user", cascade="all, delete-orphan",
                                 passive_deletes=True)

    @property
    def role_label(self) -> str:
        return ROLES.get(self.role, self.role)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_mp(self) -> bool:
        return self.role == "mp"

    @property
    def is_citizen(self) -> bool:
        return self.role == "citizen"

    @property
    def initials(self) -> str:
        return initials(self.full_name)

    @property
    def avatar_color(self) -> str:
        return avatar_color(self.email)

    @property
    def avatar_url(self) -> str | None:
        if self.mp_profile and self.mp_profile.profile_image:
            return "/static/" + self.mp_profile.profile_image
        return None


class MPProfile(Base):
    __tablename__ = "mp_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    constituency: Mapped[str] = mapped_column(String(160), default="")
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"), nullable=True)
    position: Mapped[str] = mapped_column(String(160), default="УИХ-ын гишүүн")
    bio: Mapped[str] = mapped_column(Text, default="")
    profile_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    focus_categories: Mapped[str] = mapped_column(String(255), default="")

    user: Mapped[User] = relationship(back_populates="mp_profile")
    district = relationship("District")
    khoroos = relationship("Khoroo", secondary=mp_khoroos, order_by="Khoroo.number")

    @property
    def khoroo_ids(self) -> set[int]:
        return {k.id for k in self.khoroos}

    @property
    def khoroo_numbers(self) -> list[int]:
        return [k.number for k in self.khoroos]

    @property
    def focus_list(self) -> list[str]:
        return [c for c in (self.focus_categories or "").split(",") if c]
