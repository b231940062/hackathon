"""Формын өгөгдлийн баталгаажуулалт (Pydantic). Алдааны мессежүүд монгол хэл дээр."""
import re
from datetime import date

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from app.constants import CATEGORIES, MP_SETTABLE_STATUSES, ROLES, SCOPES, URGENCY
from app.utils import local_today

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^[0-9+\-\s]{6,20}$")


def errors_of(exc: ValidationError) -> list[str]:
    messages = []
    for err in exc.errors():
        ctx_err = (err.get("ctx") or {}).get("error")
        if ctx_err is not None:
            messages.append(str(ctx_err))
        else:
            field = ".".join(str(p) for p in err.get("loc", []))
            messages.append(f"'{field}' талбарын утга буруу байна.")
    return messages


def _text(value, name: str, min_len: int, max_len: int, required: bool = True) -> str:
    value = (value or "").strip()
    if not value and not required:
        return ""
    if len(value) < min_len:
        raise ValueError(f"{name} хамгийн багадаа {min_len} тэмдэгт байх ёстой.")
    if len(value) > max_len:
        raise ValueError(f"{name} {max_len} тэмдэгтээс хэтрэхгүй байх ёстой.")
    return value


def _optional_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("Сонголт буруу байна.")


def _email(value) -> str:
    value = (value or "").strip().lower()
    if not EMAIL_RE.match(value) or len(value) > 255:
        raise ValueError("Имэйл хаяг буруу байна.")
    return value


def _password(value) -> str:
    value = value or ""
    if len(value) < 8:
        raise ValueError("Нууц үг хамгийн багадаа 8 тэмдэгт байх ёстой.")
    if len(value) > 128:
        raise ValueError("Нууц үг хэт урт байна.")
    if not re.search(r"[A-Za-zА-Яа-яӨөҮүЁё]", value) or not re.search(r"\d", value):
        raise ValueError("Нууц үг үсэг болон тоо агуулсан байх ёстой.")
    return value


def _phone(value) -> str:
    value = (value or "").strip()
    if value and not PHONE_RE.match(value):
        raise ValueError("Утасны дугаар буруу байна.")
    return value


class RegisterForm(BaseModel):
    full_name: str
    email: str
    phone: str = ""
    district_id: int | None = None
    khoroo_id: int | None = None
    password: str
    password2: str

    _v_name = field_validator("full_name")(lambda v: _text(v, "Нэр", 2, 120))
    _v_email = field_validator("email")(_email)
    _v_phone = field_validator("phone")(_phone)
    _v_pw = field_validator("password")(_password)
    _v_ids = field_validator("district_id", "khoroo_id", mode="before")(_optional_int)

    @model_validator(mode="after")
    def _match(self):
        if self.password != self.password2:
            raise ValueError("Нууц үг таарахгүй байна.")
        return self


class IssueForm(BaseModel):
    title: str
    description: str
    category: str
    district_id: int
    khoroo_id: int | None = None
    location: str = ""
    urgency: str = "medium"
    affected_scope: str = "street"
    lat: float | None = None
    lng: float | None = None

    _v_title = field_validator("title")(lambda v: _text(v, "Гарчиг", 5, 150))
    _v_desc = field_validator("description")(lambda v: _text(v, "Тайлбар", 20, 3000))
    _v_loc = field_validator("location")(lambda v: _text(v, "Байршил", 0, 200, required=False))
    _v_ids = field_validator("khoroo_id", mode="before")(_optional_int)

    @field_validator("district_id", mode="before")
    @classmethod
    def _district(cls, v):
        v = _optional_int(v)
        if v is None:
            raise ValueError("Дүүргээ сонгоно уу.")
        return v

    @field_validator("category")
    @classmethod
    def _cat(cls, v):
        if v not in CATEGORIES:
            raise ValueError("Ангилал сонгоно уу.")
        return v

    @field_validator("urgency")
    @classmethod
    def _urg(cls, v):
        if v not in URGENCY:
            raise ValueError("Яаралтай байдлын түвшин буруу байна.")
        return v

    @field_validator("affected_scope")
    @classmethod
    def _scope(cls, v):
        if v not in SCOPES:
            raise ValueError("Нөлөөллийн хүрээ буруу байна.")
        return v

    @field_validator("lat", "lng", mode="before")
    @classmethod
    def _coord(cls, v):
        if v in (None, ""):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @model_validator(mode="after")
    def _bounds(self):
        # Монгол улсын хүрээнээс гадуурх координатыг хүлээж авахгүй
        if self.lat is not None and self.lng is not None:
            if not (41.5 <= self.lat <= 52.2 and 87.7 <= self.lng <= 120.0):
                self.lat = self.lng = None
        else:
            self.lat = self.lng = None
        return self


class CommentForm(BaseModel):
    content: str
    _v = field_validator("content")(lambda v: _text(v, "Сэтгэгдэл", 2, 1000))


class ResponseForm(BaseModel):
    content: str
    kind: str = "response"
    _v = field_validator("content")(lambda v: _text(v, "Хариу", 5, 2000))

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in ("response", "update"):
            raise ValueError("Хариуны төрөл буруу байна.")
        return v


class StatusForm(BaseModel):
    status: str
    note: str = ""
    _v_note = field_validator("note")(lambda v: _text(v, "Тайлбар", 0, 500, required=False))

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v not in MP_SETTABLE_STATUSES:
            raise ValueError("Төлөв буруу байна.")
        return v


class ForwardForm(BaseModel):
    organization: str
    note: str = ""
    _v_org = field_validator("organization")(lambda v: _text(v, "Байгууллагын нэр", 3, 200))
    _v_note = field_validator("note")(lambda v: _text(v, "Тайлбар", 0, 2000, required=False))


class ResolveForm(BaseModel):
    explanation: str
    action_taken: str
    resolved_on: date
    official_response: str = ""

    _v_exp = field_validator("explanation")(lambda v: _text(v, "Тайлбар", 10, 3000))
    _v_act = field_validator("action_taken")(lambda v: _text(v, "Хийгдсэн ажил", 5, 3000))
    _v_resp = field_validator("official_response")(lambda v: _text(v, "Албан хариу", 0, 2000, required=False))

    @field_validator("resolved_on", mode="before")
    @classmethod
    def _date(cls, v):
        if v in (None, ""):
            return local_today()
        try:
            d = date.fromisoformat(str(v))
        except ValueError:
            raise ValueError("Шийдвэрлэсэн огноо буруу байна.")
        if d > local_today():
            raise ValueError("Шийдвэрлэсэн огноо ирээдүйд байж болохгүй.")
        return d


class ConfirmForm(BaseModel):
    answer: str
    reason: str = ""

    @field_validator("answer")
    @classmethod
    def _answer(cls, v):
        if v not in ("yes", "no"):
            raise ValueError("Хариултаа сонгоно уу.")
        return v

    @model_validator(mode="after")
    def _reason(self):
        self.reason = (self.reason or "").strip()[:1000]
        if self.answer == "no" and len(self.reason) < 5:
            raise ValueError("Асуудал хэвээр байгаа шалтгааныг бичнэ үү (хамгийн багадаа 5 тэмдэгт).")
        return self


class ProfileForm(BaseModel):
    full_name: str
    phone: str = ""
    district_id: int | None = None
    khoroo_id: int | None = None

    _v_name = field_validator("full_name")(lambda v: _text(v, "Нэр", 2, 120))
    _v_phone = field_validator("phone")(_phone)
    _v_ids = field_validator("district_id", "khoroo_id", mode="before")(_optional_int)


class PasswordChangeForm(BaseModel):
    current_password: str
    new_password: str
    new_password2: str
    _v_pw = field_validator("new_password")(_password)

    @model_validator(mode="after")
    def _match(self):
        if self.new_password != self.new_password2:
            raise ValueError("Шинэ нууц үг таарахгүй байна.")
        return self


class UserEditForm(BaseModel):
    full_name: str
    email: str
    role: str
    phone: str = ""
    district_id: int | None = None
    khoroo_id: int | None = None
    is_active: bool = True
    new_password: str = ""

    _v_name = field_validator("full_name")(lambda v: _text(v, "Нэр", 2, 120))
    _v_email = field_validator("email")(_email)
    _v_phone = field_validator("phone")(_phone)
    _v_ids = field_validator("district_id", "khoroo_id", mode="before")(_optional_int)

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ROLES:
            raise ValueError("Эрх буруу байна.")
        return v

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v):
        return _password(v) if v else ""


class MPForm(BaseModel):
    full_name: str
    email: str
    password: str = ""
    phone: str = ""
    constituency: str
    district_id: int | None = None
    khoroo_ids: list[int] = []
    position: str = "УИХ-ын гишүүн"
    bio: str = ""
    focus_categories: list[str] = []

    _v_name = field_validator("full_name")(lambda v: _text(v, "Нэр", 2, 120))
    _v_email = field_validator("email")(_email)
    _v_phone = field_validator("phone")(_phone)
    _v_const = field_validator("constituency")(lambda v: _text(v, "Тойргийн нэр", 2, 160))
    _v_pos = field_validator("position")(lambda v: _text(v, "Албан тушаал", 2, 160))
    _v_bio = field_validator("bio")(lambda v: _text(v, "Намтар", 0, 2000, required=False))
    _v_ids = field_validator("district_id", mode="before")(_optional_int)

    @field_validator("password")
    @classmethod
    def _pw(cls, v):
        return _password(v) if v else ""

    @field_validator("focus_categories")
    @classmethod
    def _cats(cls, v):
        return [c for c in v if c in CATEGORIES]
