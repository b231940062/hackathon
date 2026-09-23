from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import CATEGORIES, SCOPES, STATUS_INFO, STATUSES, URGENCY
from app.database import Base
from app.utils import utcnow


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), index=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), index=True)
    khoroo_id: Mapped[int | None] = mapped_column(ForeignKey("khoroos.id", ondelete="SET NULL"), nullable=True,
                                                  index=True)
    location: Mapped[str] = mapped_column(String(200), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    urgency: Mapped[str] = mapped_column(String(16), default="medium")
    affected_scope: Mapped[str] = mapped_column(String(16), default="street")
    status: Mapped[str] = mapped_column(String(20), default="NEW", index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
                                                  index=True)
    # Хариуцах УИХ-ын гишүүн (тойргоор автоматаар тодорхойлогдох, гишүүн хүлээн авснаар баталгаажна)
    mp_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    forwarded_to: Mapped[str | None] = mapped_column(String(200), nullable=True)
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    priority_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    district = relationship("District")
    khoroo = relationship("Khoroo")
    author = relationship("User", foreign_keys=[author_id], back_populates="issues")
    mp = relationship("User", foreign_keys=[mp_id])
    images: Mapped[list["IssueImage"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", passive_deletes=True, order_by="IssueImage.id")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", passive_deletes=True, order_by="Comment.created_at")
    supports: Mapped[list["Support"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", passive_deletes=True)
    responses: Mapped[list["OfficialResponse"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", passive_deletes=True,
        order_by="OfficialResponse.created_at")
    history: Mapped[list["IssueStatusHistory"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", passive_deletes=True,
        order_by="IssueStatusHistory.created_at")
    resolution: Mapped["Resolution | None"] = relationship(
        back_populates="issue", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    confirmations: Mapped[list["ResolutionConfirmation"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ResolutionConfirmation.created_at")
    notifications = relationship("Notification", back_populates="issue", cascade="all, delete-orphan",
                                 passive_deletes=True)

    # ---- Дэлгэцэнд харуулах туслах шинжүүд ----
    @property
    def status_info(self) -> dict:
        return STATUS_INFO.get(self.status, STATUS_INFO["NEW"])

    @property
    def status_index(self) -> int:
        return STATUSES.index(self.status) if self.status in STATUSES else 0

    @property
    def category_info(self) -> dict:
        return CATEGORIES.get(self.category, CATEGORIES["other"])

    @property
    def urgency_label(self) -> str:
        return URGENCY.get(self.urgency, URGENCY["medium"])["label"]

    @property
    def scope_label(self) -> str:
        return SCOPES.get(self.affected_scope, SCOPES["street"])["label"]

    @property
    def is_resolved(self) -> bool:
        return self.status == "RESOLVED"

    def _image(self, kind: str) -> "IssueImage | None":
        for img in self.images:
            if img.kind == kind:
                return img
        return None

    @property
    def cover_image(self) -> str | None:
        img = self._image("original")
        return img.path if img else None

    @property
    def before_image(self) -> str | None:
        img = self._image("before") or self._image("original")
        return img.path if img else None

    @property
    def after_image(self) -> str | None:
        img = None
        for candidate in self.images:
            if candidate.kind == "after":
                img = candidate  # хамгийн сүүлийн "дараа" зураг
        return img.path if img else None

    @property
    def location_label(self) -> str:
        parts = [self.district.name if self.district else ""]
        if self.khoroo:
            parts.append(self.khoroo.label)
        return " · ".join(p for p in parts if p)

    @property
    def official_responses(self) -> list["OfficialResponse"]:
        return [r for r in self.responses if r.kind in ("response", "forward", "resolution", "update")]

    @property
    def visible_comments(self) -> list["Comment"]:
        return list(self.comments)

    @property
    def confirmation_stats(self) -> dict:
        yes = sum(1 for c in self.confirmations if c.is_resolved)
        no = sum(1 for c in self.confirmations if not c.is_resolved)
        total = yes + no
        author_answer = None
        for c in self.confirmations:
            if c.user_id == self.author_id:
                author_answer = c.is_resolved
        return {"yes": yes, "no": no, "total": total,
                "yes_pct": round(yes * 100 / total) if total else 0,
                "author_answer": author_answer,
                "disputed": self.is_resolved and (author_answer is False or (total >= 2 and no > yes))}


class IssueImage(Base):
    __tablename__ = "issue_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(255))
    # original: иргэний оруулсан | before/after: шийдвэрлэлтийн нотолгоо | followup: иргэний давтан зураг
    kind: Mapped[str] = mapped_column(String(16), default="original")
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    issue: Mapped[Issue] = relationship(back_populates="images")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    issue: Mapped[Issue] = relationship(back_populates="comments")
    user = relationship("User", back_populates="comments")


class Support(Base):
    __tablename__ = "supports"
    __table_args__ = (UniqueConstraint("issue_id", "user_id", name="uq_support_issue_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    issue: Mapped[Issue] = relationship(back_populates="supports")
    user = relationship("User", back_populates="supports")


class OfficialResponse(Base):
    __tablename__ = "official_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # response: албан хариу | update: явцын мэдээ | forward: байгууллагад шилжүүлсэн | resolution: шийдвэрлэлт
    kind: Mapped[str] = mapped_column(String(16), default="response")
    content: Mapped[str] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    issue: Mapped[Issue] = relationship(back_populates="responses")
    author = relationship("User")

    KIND_LABELS = {
        "response": "Албан ёсны хариу",
        "update": "Явцын мэдээлэл",
        "forward": "Байгууллагад шилжүүлсэн",
        "resolution": "Шийдвэрлэлтийн хариу",
    }

    @property
    def kind_label(self) -> str:
        return self.KIND_LABELS.get(self.kind, "Албан ёсны хариу")


class IssueStatusHistory(Base):
    __tablename__ = "issue_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20))
    changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    issue: Mapped[Issue] = relationship(back_populates="history")
    changed_by = relationship("User")

    @property
    def new_info(self) -> dict:
        return STATUS_INFO.get(self.new_status, STATUS_INFO["NEW"])

    @property
    def old_info(self) -> dict | None:
        return STATUS_INFO.get(self.old_status) if self.old_status else None


class Resolution(Base):
    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), unique=True)
    explanation: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(Text)
    resolved_on: Mapped[date] = mapped_column(Date)
    official_response: Mapped[str] = mapped_column(Text, default="")
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    issue: Mapped[Issue] = relationship(back_populates="resolution")
    resolved_by = relationship("User")


class ResolutionConfirmation(Base):
    __tablename__ = "resolution_confirmations"
    __table_args__ = (UniqueConstraint("issue_id", "user_id", name="uq_confirmation_issue_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    issue: Mapped[Issue] = relationship(back_populates="confirmations")
    user = relationship("User", back_populates="confirmations")
