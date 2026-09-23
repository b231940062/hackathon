from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, role_home
from app.auth.security import hash_password, verify_password
from app.config import settings
from app.database import get_db
from app.models import Khoroo, User
from app.schemas.forms import RegisterForm, errors_of
from app.services import ratelimit
from app.services import settings as cfg
from app.services.issues import districts_payload
from app.templating import flash, render
from app.utils import safe_next, utcnow

router = APIRouter()

DEMO_ACCOUNTS = [
    {"role": "Иргэн", "icon": "🙋", "email": "citizen@holboos.mn", "name": "Д.Сарангэрэл · Баянзүрх, 26-р хороо"},
    {"role": "УИХ-ын гишүүн", "icon": "🏛️", "email": "mp@holboos.mn", "name": "Г.Бат-Эрдэнэ · Баянзүрх тойрог"},
    {"role": "Админ", "icon": "🛡️", "email": "admin@holboos.mn", "name": "Платформын удирдлага"},
    {"role": "Иргэн 2", "icon": "🙋‍♂️", "email": "bold@holboos.mn", "name": "Б.Болд · Баянзүрх, 3-р хороо"},
]


def _login_context(db: Session, **extra) -> dict:
    demo = cfg.get_bool(db, "demo_mode")
    return {"demo_accounts": DEMO_ACCOUNTS if demo else [],
            "demo_password": settings.demo_password if demo else "", **extra}


@router.get("/login")
def login_page(request: Request, next: str = "", user: User | None = Depends(get_current_user),
               db: Session = Depends(get_db)):
    if user:
        return RedirectResponse(role_home(user), status_code=303)
    return render(request, "auth/login.html", _login_context(db, next=next))


@router.post("/login")
def login(request: Request, email: str = Form(""), password: str = Form(""), next: str = Form(""),
          db: Session = Depends(get_db)):
    ip = ratelimit.client_ip(request)
    if not ratelimit.allow(f"login:{ip}", limit=10, window_seconds=300):
        return render(request, "auth/login.html", _login_context(
            db, next=next, email=email, error="Хэт олон оролдлого хийлээ. 5 минутын дараа дахин оролдоно уу."),
            status_code=429)
    email = (email or "").strip().lower()[:255]
    user = db.scalar(select(User).where(User.email == email))
    if not verify_password(user.password_hash if user else None, password or ""):
        return render(request, "auth/login.html", _login_context(
            db, next=next, email=email, error="Имэйл эсвэл нууц үг буруу байна."), status_code=400)
    if not user.is_active:
        return render(request, "auth/login.html", _login_context(
            db, next=next, email=email, error="Таны бүртгэл түр хаагдсан байна. Админтай холбогдоно уу."),
            status_code=403)
    request.session.clear()  # session fixation-аас сэргийлнэ
    request.session["uid"] = user.id
    user.last_login_at = utcnow()
    db.commit()
    flash(request, f"Тавтай морил, {user.full_name}!")
    return RedirectResponse(safe_next(next, role_home(user)), status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    flash(request, "Та системээс гарлаа.", "info")
    return RedirectResponse("/", status_code=303)


@router.get("/register")
def register_page(request: Request, user: User | None = Depends(get_current_user), db: Session = Depends(get_db)):
    if user:
        return RedirectResponse(role_home(user), status_code=303)
    return render(request, "auth/register.html", {"districts": districts_payload(db), "form": {},
                                                  "allow": cfg.get_bool(db, "allow_registration")})


@router.post("/register")
def register(request: Request, full_name: str = Form(""), email: str = Form(""), phone: str = Form(""),
             district_id: str = Form(""), khoroo_id: str = Form(""), password: str = Form(""),
             password2: str = Form(""), db: Session = Depends(get_db)):
    raw = {"full_name": full_name, "email": email, "phone": phone, "district_id": district_id,
           "khoroo_id": khoroo_id}
    ctx = {"districts": districts_payload(db), "form": raw, "allow": cfg.get_bool(db, "allow_registration")}
    if not ctx["allow"]:
        return render(request, "auth/register.html", {**ctx, "errors": ["Шинэ бүртгэл түр хаалттай байна."]},
                      status_code=403)
    if not ratelimit.allow(f"register:{ratelimit.client_ip(request)}", limit=5, window_seconds=600):
        return render(request, "auth/register.html", {**ctx, "errors": ["Хэт олон оролдлого. Түр хүлээнэ үү."]},
                      status_code=429)
    try:
        data = RegisterForm(full_name=full_name, email=email, phone=phone, district_id=district_id,
                            khoroo_id=khoroo_id, password=password, password2=password2)
    except ValidationError as e:
        return render(request, "auth/register.html", {**ctx, "errors": errors_of(e)}, status_code=400)
    if data.khoroo_id:
        k = db.get(Khoroo, data.khoroo_id)
        if k is None or k.district_id != data.district_id:
            return render(request, "auth/register.html", {**ctx, "errors": ["Хороо буруу сонгогдсон байна."]},
                          status_code=400)
    if db.scalar(select(User.id).where(User.email == data.email)):
        return render(request, "auth/register.html", {**ctx, "errors": ["Энэ имэйлээр бүртгэл үүссэн байна."]},
                      status_code=400)
    user = User(full_name=data.full_name, email=data.email, phone=data.phone or None, role="citizen",
                district_id=data.district_id, khoroo_id=data.khoroo_id, password_hash=hash_password(data.password),
                last_login_at=utcnow())
    db.add(user)
    db.commit()
    request.session.clear()
    request.session["uid"] = user.id
    flash(request, "Бүртгэл амжилттай үүслээ. Холбоос-д тавтай морил!")
    return RedirectResponse("/issues", status_code=303)
