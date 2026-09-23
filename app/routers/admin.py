"""Админ самбар. Бүх зам зөвхөн "admin" эрхтэй хэрэглэгчид нээлттэй (router түвшинд хамгаалсан)."""
import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth.deps import require_admin
from app.auth.security import hash_password
from app.constants import CATEGORIES, ROLES, STATUS_INFO, STATUSES
from app.database import ci_contains, get_db
from app.models import (Comment, District, Issue, IssueStatusHistory, Khoroo, MPProfile, Support, User)
from app.schemas.forms import MPForm, UserEditForm, errors_of
from app.services import settings as cfg
from app.services import stats as stats_svc
from app.services.issues import (active_mp_profiles, build_activity, build_timeline, delete_issue, districts_payload,
                                 issue_query, load_issue_full, refresh_counts)
from app.services.charts import grouped_columns
from app.services.uploads import UploadError, save_image
from app.templating import flash, render
from app.utils import fmt_datetime, parse_int

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
PER_PAGE = 25


def _pages(total: int, page: int) -> dict:
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    return {"page": min(page, pages), "pages": pages, "total": total}


# ---------- Самбар ----------
@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db)):
    recent = db.scalars(select(IssueStatusHistory)
                        .options(joinedload(IssueStatusHistory.issue), joinedload(IssueStatusHistory.changed_by))
                        .order_by(IssueStatusHistory.created_at.desc()).limit(12)).all()
    new_users = db.scalars(select(User).order_by(User.created_at.desc()).limit(6)).all()
    return render(request, "admin/dashboard.html", {
        "stats": stats_svc.platform_stats(db), "weekly": grouped_columns(stats_svc.weekly_counts(db, 10)),
        "districts": stats_svc.district_breakdown(db), "categories": stats_svc.category_breakdown(db),
        "recent": recent, "new_users": new_users, "mp_perf": stats_svc.mp_performance(db)[:5],
    })


# ---------- Хэрэглэгчид ----------
@router.get("/users")
def users(request: Request, q: str = "", role: str = "", status: str = "", page: int = 1,
          db: Session = Depends(get_db)):
    stmt = select(User).options(joinedload(User.district))
    q = q.strip()[:100]
    if q:
        stmt = stmt.where(or_(ci_contains(User.full_name, q), ci_contains(User.email, q), ci_contains(User.phone, q)))
    if role in ROLES:
        stmt = stmt.where(User.role == role)
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "blocked":
        stmt = stmt.where(User.is_active.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    pg = _pages(total, max(1, page))
    rows = db.scalars(stmt.order_by(User.created_at.desc()).offset((pg["page"] - 1) * PER_PAGE)
                      .limit(PER_PAGE)).all()
    counts = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    return render(request, "admin/users.html", {"users": rows, "q": q, "role": role, "status": status,
                                                "counts": counts, **pg})


@router.get("/users/{user_id}/edit")
def user_edit_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    target = db.get(User, user_id) or _404()
    return render(request, "admin/user_edit.html", {"target": target, "districts": districts_payload(db),
                                                    "form": None})


@router.post("/users/{user_id}/edit")
def user_edit(user_id: int, request: Request, full_name: str = Form(""), email: str = Form(""),
              role: str = Form("citizen"), phone: str = Form(""), district_id: str = Form(""),
              khoroo_id: str = Form(""), is_active: str = Form(""), new_password: str = Form(""),
              admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id) or _404()
    raw = {"full_name": full_name, "email": email, "role": role, "phone": phone, "district_id": district_id,
           "khoroo_id": khoroo_id, "is_active": is_active == "1", "new_password": new_password}

    def fail(errors):
        return render(request, "admin/user_edit.html", {"target": target, "districts": districts_payload(db),
                                                        "form": raw, "errors": errors}, status_code=400)
    try:
        data = UserEditForm(**raw)
    except ValidationError as e:
        return fail(errors_of(e))
    if target.id == admin.id and (data.role != "admin" or not data.is_active):
        return fail(["Өөрийн админ эрхийг хасах эсвэл өөрийгөө хаах боломжгүй."])
    if db.scalar(select(User.id).where(User.email == data.email, User.id != target.id)):
        return fail(["Энэ имэйл өөр хэрэглэгчид бүртгэлтэй байна."])
    if data.khoroo_id:
        k = db.get(Khoroo, data.khoroo_id)
        if k is None or k.district_id != data.district_id:
            return fail(["Хороо буруу сонгогдсон байна."])
    target.full_name, target.email, target.phone = data.full_name, data.email, data.phone or None
    target.district_id, target.khoroo_id, target.is_active = data.district_id, data.khoroo_id, data.is_active
    _apply_role(db, target, data.role)
    if data.new_password:
        target.password_hash = hash_password(data.new_password)
    db.commit()
    flash(request, f"{target.full_name}-ийн мэдээлэл шинэчлэгдлээ.")
    return RedirectResponse("/admin/users", status_code=303)


def _apply_role(db: Session, target: User, role: str) -> None:
    target.role = role
    if role == "mp" and target.mp_profile is None:
        district = db.get(District, target.district_id) if target.district_id else None
        target.mp_profile = MPProfile(district_id=target.district_id,
                                      constituency=f"{district.name} дүүргийн тойрог" if district else "Тодорхойгүй")


@router.post("/users/{user_id}/role")
def user_role(user_id: int, request: Request, role: str = Form(""), admin: User = Depends(require_admin),
              db: Session = Depends(get_db)):
    target = db.get(User, user_id) or _404()
    if role not in ROLES:
        flash(request, "Эрх буруу байна.", "error")
    elif target.id == admin.id:
        flash(request, "Өөрийн эрхийг өөрчлөх боломжгүй.", "error")
    else:
        _apply_role(db, target, role)
        db.commit()
        flash(request, f"{target.full_name}-ийн эрх: {ROLES[role]}.")
        if role == "mp":
            flash(request, "Гишүүний тойрог, хороог \"УИХ-ын гишүүд\" хэсгээс тохируулна уу.", "info")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
def user_delete(user_id: int, request: Request, next: str = Form("/admin/users"), admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    target = db.get(User, user_id) or _404()
    if target.id == admin.id:
        flash(request, "Өөрийгөө устгах боломжгүй.", "error")
        return RedirectResponse("/admin/users", status_code=303)
    touched = set(db.scalars(select(Support.issue_id).where(Support.user_id == target.id)))
    touched |= set(db.scalars(select(Comment.issue_id).where(Comment.user_id == target.id)))
    name = target.full_name
    db.delete(target)
    db.flush()
    for issue in db.scalars(select(Issue).where(Issue.id.in_(touched))):
        refresh_counts(db, issue)
    db.commit()
    flash(request, f"{name} хэрэглэгч устгагдлаа.")
    return RedirectResponse(next if next in ("/admin/users", "/admin/mps") else "/admin/users", status_code=303)


# ---------- УИХ-ын гишүүд ----------
@router.get("/mps")
def mps(request: Request, db: Session = Depends(get_db)):
    profiles = db.scalars(select(MPProfile).join(User, User.id == MPProfile.user_id).where(User.role == "mp")
                          .options(joinedload(MPProfile.user), joinedload(MPProfile.district),
                                   selectinload(MPProfile.khoroos)).order_by(MPProfile.id)).unique().all()
    perf = {p["user"].id: p for p in stats_svc.mp_performance(db)}
    covered = {p.district_id for p in profiles if p.district_id} or {0}
    uncovered = db.scalars(select(District).where(District.id.not_in(covered))).all()
    return render(request, "admin/mps.html", {"profiles": profiles, "perf": perf, "uncovered": uncovered})


def _mp_form_ctx(db: Session, target: User | None, form: dict | None, errors=None) -> dict:
    return {"target": target, "profile": target.mp_profile if target else None, "form": form,
            "districts": districts_payload(db), "errors": errors or []}


@router.get("/mps/new")
def mp_new_page(request: Request, db: Session = Depends(get_db)):
    return render(request, "admin/mp_form.html", _mp_form_ctx(db, None, None))


@router.get("/mps/{user_id}/edit")
def mp_edit_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    target = _mp_or_404(db, user_id)
    return render(request, "admin/mp_form.html", _mp_form_ctx(db, target, None))


def _mp_or_404(db: Session, user_id: int) -> User:
    target = db.scalar(select(User).where(User.id == user_id)
                       .options(joinedload(User.mp_profile).selectinload(MPProfile.khoroos)))
    if target is None or target.mp_profile is None:
        _404()
    return target


class MPFormFields:
    """Гишүүн нэмэх/засах формын талбарууд (хоёр маршрутад дахин ашиглана)."""

    def __init__(self, full_name: str = Form(""), email: str = Form(""), password: str = Form(""),
                 phone: str = Form(""), constituency: str = Form(""), district_id: str = Form(""),
                 khoroo_ids: list[str] = Form([]), position: str = Form("УИХ-ын гишүүн"), bio: str = Form(""),
                 focus_categories: list[str] = Form([]), profile_image: UploadFile | None = File(None)):
        self.raw = {"full_name": full_name, "email": email, "password": password, "phone": phone,
                    "constituency": constituency, "district_id": district_id,
                    "khoroo_ids": [parse_int(k) for k in khoroo_ids if parse_int(k)], "position": position,
                    "bio": bio, "focus_categories": focus_categories}
        self.profile_image = profile_image


@router.post("/mps/new")
def mp_create(request: Request, fields: MPFormFields = Depends(), db: Session = Depends(get_db)):
    return _mp_save(request, db, None, fields)


@router.post("/mps/{user_id}/edit")
def mp_update(user_id: int, request: Request, fields: MPFormFields = Depends(), db: Session = Depends(get_db)):
    return _mp_save(request, db, _mp_or_404(db, user_id), fields)


def _mp_save(request: Request, db: Session, target: User | None, fields: MPFormFields):
    raw, profile_image = fields.raw, fields.profile_image

    def fail(errors):
        return render(request, "admin/mp_form.html", _mp_form_ctx(db, target, raw, errors), status_code=400)
    try:
        data = MPForm(**raw)
    except ValidationError as e:
        return fail(errors_of(e))
    if target is None and not data.password:
        return fail(["Шинэ гишүүнд анхны нууц үг оноох шаардлагатай."])
    if db.scalar(select(User.id).where(User.email == data.email, User.id != (target.id if target else 0))):
        return fail(["Энэ имэйл өөр хэрэглэгчид бүртгэлтэй байна."])
    khoroos = db.scalars(select(Khoroo).where(Khoroo.id.in_(data.khoroo_ids))).all() if data.khoroo_ids else []
    if data.district_id and any(k.district_id != data.district_id for k in khoroos):
        return fail(["Сонгосон хороод тухайн дүүрэгт хамаарах ёстой."])
    try:
        image_path = save_image(profile_image, "profiles", max_side=600)
    except UploadError as e:
        return fail([str(e)])
    if target is None:
        target = User(role="mp", password_hash=hash_password(data.password), full_name=data.full_name,
                      email=data.email)
        target.mp_profile = MPProfile()
        db.add(target)
    target.full_name, target.email, target.phone = data.full_name, data.email, data.phone or None
    target.district_id = data.district_id
    if data.password and target.id:
        target.password_hash = hash_password(data.password)
    p = target.mp_profile
    p.constituency, p.district_id, p.position, p.bio = data.constituency, data.district_id, data.position, data.bio
    p.focus_categories = ",".join(data.focus_categories)
    p.khoroos = list(khoroos)
    if image_path:
        p.profile_image = image_path
    db.commit()
    flash(request, f"{target.full_name} гишүүний мэдээлэл хадгалагдлаа.")
    return RedirectResponse("/admin/mps", status_code=303)


# ---------- Асуудлууд ----------
@router.get("/issues")
def issues(request: Request, q: str = "", status: str = "", district: str = "", page: int = 1,
           db: Session = Depends(get_db)):
    stmt = issue_query()
    q = q.strip()[:100]
    if q:
        stmt = stmt.where(or_(ci_contains(Issue.title, q), ci_contains(Issue.description, q)))
    if status in STATUSES:
        stmt = stmt.where(Issue.status == status)
    did = parse_int(district)
    if did:
        stmt = stmt.where(Issue.district_id == did)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    pg = _pages(total, max(1, page))
    rows = db.scalars(stmt.order_by(Issue.created_at.desc()).offset((pg["page"] - 1) * PER_PAGE)
                      .limit(PER_PAGE)).unique().all()
    return render(request, "admin/issues.html", {
        "issues": rows, "q": q, "status": status, "district": did or "",
        "districts": db.scalars(select(District).order_by(District.id)).all(), **pg})


@router.get("/issues/{issue_id}")
def issue_audit(issue_id: int, request: Request, db: Session = Depends(get_db)):
    issue = load_issue_full(db, issue_id) or _404()
    supporters = db.scalars(select(Support).where(Support.issue_id == issue.id).options(joinedload(Support.user))
                            .order_by(Support.created_at.desc()).limit(12)).all()
    return render(request, "admin/issue_detail.html", {
        "issue": issue, "timeline": build_timeline(issue), "activity": build_activity(issue, include_comments=True),
        "supporters": supporters, "mps": active_mp_profiles(db), "conf": issue.confirmation_stats,
    })


@router.post("/issues/{issue_id}/assign")
def issue_assign(issue_id: int, request: Request, mp_id: str = Form(""), db: Session = Depends(get_db)):
    issue = db.get(Issue, issue_id) or _404()
    new_id = parse_int(mp_id)
    if new_id:
        mp = db.get(User, new_id)
        if mp is None or mp.role != "mp":
            flash(request, "Гишүүн олдсонгүй.", "error")
            return RedirectResponse(f"/admin/issues/{issue_id}", status_code=303)
        issue.mp_id = mp.id
        from app.services.notifications import notify
        notify(db, mp.id, "system", f"Админ танд \"{issue.title}\" асуудлыг хариуцуулж оноолоо.", issue.id)
        flash(request, f"Хариуцах гишүүн: {mp.full_name}")
    else:
        issue.mp_id = None
        flash(request, "Хариуцах гишүүнийг цуцаллаа.", "info")
    db.commit()
    return RedirectResponse(f"/admin/issues/{issue_id}", status_code=303)


@router.post("/issues/{issue_id}/delete")
def issue_delete(issue_id: int, request: Request, db: Session = Depends(get_db)):
    issue = db.get(Issue, issue_id) or _404()
    title = issue.title
    delete_issue(db, issue)
    db.commit()
    flash(request, f"\"{title}\" асуудал устгагдлаа.")
    return RedirectResponse("/admin/issues", status_code=303)


# ---------- Сэтгэгдэл ----------
@router.get("/comments")
def comments(request: Request, q: str = "", show: str = "all", page: int = 1, db: Session = Depends(get_db)):
    stmt = select(Comment).options(joinedload(Comment.user), joinedload(Comment.issue))
    q = q.strip()[:100]
    if q:
        stmt = stmt.where(ci_contains(Comment.content, q))
    if show == "hidden":
        stmt = stmt.where(Comment.is_hidden.is_(True))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    pg = _pages(total, max(1, page))
    rows = db.scalars(stmt.order_by(Comment.created_at.desc()).offset((pg["page"] - 1) * PER_PAGE)
                      .limit(PER_PAGE)).all()
    hidden = db.scalar(select(func.count()).select_from(Comment).where(Comment.is_hidden.is_(True)))
    return render(request, "admin/comments.html", {"comments": rows, "q": q, "show": show, "hidden": hidden, **pg})


@router.post("/comments/{comment_id}/{action}")
def comment_action(comment_id: int, action: str, request: Request, next: str = Form("/admin/comments"),
                   db: Session = Depends(get_db)):
    c = db.get(Comment, comment_id) or _404()
    issue = db.get(Issue, c.issue_id)
    if action == "hide":
        c.is_hidden = True
        msg = "Сэтгэгдлийг нуулаа."
    elif action == "unhide":
        c.is_hidden = False
        msg = "Сэтгэгдлийг сэргээлээ."
    elif action == "delete":
        db.delete(c)
        msg = "Сэтгэгдэл устгагдлаа."
    else:
        raise HTTPException(404)
    if issue:
        refresh_counts(db, issue)
    db.commit()
    flash(request, msg)
    return RedirectResponse(next if next.startswith("/admin/") else "/admin/comments", status_code=303)


# ---------- Тайлан ----------
@router.get("/reports")
def reports(request: Request, db: Session = Depends(get_db)):
    return render(request, "admin/reports.html", {
        "stats": stats_svc.platform_stats(db), "districts": stats_svc.district_breakdown(db),
        "categories": stats_svc.category_breakdown(db), "mp_perf": stats_svc.mp_performance(db),
    })


def _csv_safe(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text  # CSV/Excel формула шахалтаас хамгаална


@router.get("/reports/export.csv")
def export_csv(db: Session = Depends(get_db)):
    rows = db.scalars(issue_query().order_by(Issue.id)).unique().all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "Гарчиг", "Ангилал", "Дүүрэг", "Хороо", "Төлөв", "Дэмжлэг", "Сэтгэгдэл", "Ач холбогдол",
                     "Хариуцах гишүүн", "Шилжүүлсэн байгууллага", "Үүсгэсэн", "Шийдвэрлэсэн"])
    for i in rows:
        writer.writerow([_csv_safe(v) for v in [
            i.id, i.title, i.category_info["label"], i.district.name if i.district else "",
            i.khoroo.number if i.khoroo else "", STATUS_INFO[i.status]["label"], i.support_count, i.comment_count,
            i.priority_score, i.mp.full_name if i.mp else "", i.forwarded_to or "", fmt_datetime(i.created_at),
            fmt_datetime(i.resolved_at)]])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=holboos_issues.csv"})


# ---------- Тохиргоо ----------
@router.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db)):
    values = {k: cfg.get_setting(db, k) for k in cfg.DEFAULTS}
    return render(request, "admin/settings.html", {"values": values, "labels": cfg.LABELS})


@router.post("/settings")
def settings_save(request: Request, site_announcement: str = Form(""), high_priority_threshold: str = Form("70"),
                  high_support_threshold: str = Form("25"), duplicate_threshold: str = Form("0.55"),
                  allow_registration: str = Form(""), demo_mode: str = Form(""), db: Session = Depends(get_db)):
    errors = []
    hp, hs = parse_int(high_priority_threshold), parse_int(high_support_threshold)
    try:
        dup = float(duplicate_threshold)
    except ValueError:
        dup = -1
    if hp is None or not 1 <= hp <= 100:
        errors.append("Ач холбогдлын босго 1–100 хооронд байна.")
    if hs is None or not 1 <= hs <= 100000:
        errors.append("Дэмжлэгийн босго эерэг тоо байна.")
    if not 0.3 <= dup <= 0.95:
        errors.append("Давхардлын босго 0.3–0.95 хооронд байна.")
    if errors:
        values = {"site_announcement": site_announcement, "high_priority_threshold": high_priority_threshold,
                  "high_support_threshold": high_support_threshold, "duplicate_threshold": duplicate_threshold,
                  "allow_registration": "1" if allow_registration else "0", "demo_mode": "1" if demo_mode else "0"}
        return render(request, "admin/settings.html", {"values": values, "labels": cfg.LABELS, "errors": errors},
                      status_code=400)
    cfg.set_setting(db, "site_announcement", site_announcement.strip()[:300])
    cfg.set_setting(db, "high_priority_threshold", str(hp))
    cfg.set_setting(db, "high_support_threshold", str(hs))
    cfg.set_setting(db, "duplicate_threshold", f"{dup:.2f}")
    cfg.set_setting(db, "allow_registration", "1" if allow_registration else "0")
    cfg.set_setting(db, "demo_mode", "1" if demo_mode else "0")
    db.commit()
    flash(request, "Тохиргоо хадгалагдлаа.")
    return RedirectResponse("/admin/settings", status_code=303)


def _404():
    raise HTTPException(404)
