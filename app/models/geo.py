from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class District(Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    name_en: Mapped[str] = mapped_column(String(64))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)

    khoroos: Mapped[list["Khoroo"]] = relationship(
        back_populates="district", cascade="all, delete-orphan", order_by="Khoroo.number")

    @property
    def full_name(self) -> str:
        return f"{self.name} дүүрэг"


class Khoroo(Base):
    __tablename__ = "khoroos"
    __table_args__ = (UniqueConstraint("district_id", "number", name="uq_khoroo_district_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)

    district: Mapped[District] = relationship(back_populates="khoroos")

    @property
    def label(self) -> str:
        return f"{self.number}-р хороо"
