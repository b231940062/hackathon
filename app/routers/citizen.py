"""Миний асуудлууд, мэдэгдэл, профайл."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.auth.deps import login_required, require_citizen
from app.auth.security import hash_password, verify_password
from app.database import get_db
from app.models import Comment, Issue, Khoroo, Notification, ResolutionConfirmation, Support, User
from app.schemas.forms import PasswordChangeForm, ProfileForm, errors_of
from app.services.issues import districts_payload, find_relevant_mp, issue_query, supported_ids
from app.templating import flash, render

router = APIRouter()


@router.get("/my-issues")
def my_issues(request: Request, tab: str = "reported", user: User = Depends(require_citizen),
              db: Session = Depends(get_db)):
    reported = db.scalars(issue_query().where(Issue.author_id == user.id)
                          .order_by(Issue.created_at.desc())).unique().all()
    backed = db.scalars(issue_query().join(Support, Support.issue_id == Issue.id)
                        .where(Support.user_id == user.id, Issue.author_id != user.id)
                        .order_by(Support.created_at.desc())).unique().all()
    confirmed_ids = set(db.scalars(select(ResolutionConfirmation.issue_id)
                                   .where(ResolutionConfirmation.user_id == user.id)))
    to_confirm = [i for i in reported + backed if i.is_resolved and i.id not in confirmed_ids]
    if tab not in ("reported", "supported", "confirm"):
        tab = "reported"
    shown = {"reported": reported, "supported": backed, "confirm": to_confirm}[tab]
    stats = {
        "reported": len(reported),
        "resolved": sum(1 for i in reported if i.is_resolved),
        "active": sum(1 for i in reported if not i.is_resolved),
        "supports": len(backed),
        "comments": db.scalar(select(func.count()).select_from(Comment).where(Comment.user_id == user.id)) or 0,
    }
    return render(request, "citizen/my_issues.html", {
        "tab": tab, "issues": shown, "stats": stats, "to_confirm_count": len(to_confirm),
        "supported": supported_ids(db, user, [i.id for i in shown]),
    })


@router.get("/notifications")
def notifications(request: Request, user: User = Depends(login_required), db: Session = Depends(get_db)):
    items = db.scalars(select(Notification).where(Notification.user_id == user.id)
                       .options(joinedload(Notification.issue))
                       .order_by(Notification.created_at.desc()).limit(100)).all()
    return render(request, "citizen/notifications.html", {"items": items})


@router.post("/notifications/read-all")
def notifications_read_all(request: Request, user: User = Depends(login_required), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.user_id == user.id, Notification.is_read.is_(False))
               .values(is_read=True))
    db.commit()
    flash(request, "Бүх мэдэгдлийг уншсан болголоо.", "info")
    return RedirectResponse("/notifications", status_code=303)


@router.get("/notifications/{nid}/open")
def notification_open(nid: int, user: User = Depends(login_required), db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    if n is None or n.user_id != user.id:
        raise HTTPException(404)
    n.is_read = True
    db.commit()
    return RedirectResponse(f"/issues/{n.issue_id}" if n.issue_id else "/notifications", status_code=303)


def _profile_ctx(db: Session, user: User, **extra) -> dict:
    my_mp = find_relevant_mp(db, user.district_id, user.khoroo_id) if user.is_citizen and user.district_id else None
    counts = {
        "issues": db.scalar(select(func.count()).select_from(Issue).where(Issue.author_id == user.id)) or 0,
        "supports": db.scalar(select(func.count()).select_from(Support).where(Support.user_id == user.id)) or 0,
        "comments": db.scalar(select(func.count()).select_from(Comment).where(Comment.user_id == user.id)) or 0,
    }
    return {"districts": districts_payload(db), "my_mp": my_mp, "counts": counts, **extra}


@router.get("/profile")
def profile(request: Request, user: User = Depends(login_required), db: Session = Depends(get_db)):
    return render(request, "citizen/profile.html", _profile_ctx(db, user))


@router.post("/profile")
def profile_update(request: Request, full_name: str = Form(""), phone: str = Form(""), district_id: str = Form(""),
                   khoroo_id: str = Form(""), user: User = Depends(login_required), db: Session = Depends(get_db)):
    try:
        data = ProfileForm(full_name=full_name, phone=phone, district_id=district_id, khoroo_id=khoroo_id)
    except ValidationError as e:
        return render(request, "citizen/profile.html", _profile_ctx(db, user, errors=errors_of(e)), status_code=400)
    if data.khoroo_id:
        k = db.get(Khoroo, data.khoroo_id)
        if k is None or k.district_id != data.district_id:
            return render(request, "citizen/profile.html",
                          _profile_ctx(db, user, errors=["Хороо буруу сонгогдсон байна."]), status_code=400)
    user.full_name = data.full_name
    user.phone = data.phone or None
    if not user.is_mp:  # гишүүний тойргийг зөвхөн админ өөрчилнө
        user.district_id = data.district_id
        user.khoroo_id = data.khoroo_id
    db.commit()
    flash(request, "Профайл шинэчлэгдлээ.")
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/password")
def change_password(request: Request, current_password: str = Form(""), new_password: str = Form(""),
                    new_password2: str = Form(""), user: User = Depends(login_required),
                    db: Session = Depends(get_db)):
    try:
        data = PasswordChangeForm(current_password=current_password, new_password=new_password,
                                  new_password2=new_password2)
    except ValidationError as e:
        return render(request, "citizen/profile.html", _profile_ctx(db, user, pw_errors=errors_of(e)),
                      status_code=400)
    if not verify_password(user.password_hash, data.current_password):
        return render(request, "citizen/profile.html",
                      _profile_ctx(db, user, pw_errors=["Одоогийн нууц үг буруу байна."]), status_code=400)
    user.password_hash = hash_password(data.new_password)
    db.commit()
    flash(request, "Нууц үг амжилттай солигдлоо.")
    return RedirectResponse("/profile", status_code=303)
