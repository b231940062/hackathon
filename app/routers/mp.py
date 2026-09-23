"""УИХ-ын гишүүний самбар ба үйлдлүүд. Бүх зам зөвхөн "mp" эрхтэй хэрэглэгчид нээлттэй."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth.deps import Forbidden, require_mp
from app.constants import ACTIVE_STATUSES, CATEGORIES, STATUS_INFO, STATUSES
from app.database import get_db
from app.models import Issue, IssueImage, MPProfile, OfficialResponse, Resolution, User
from app.schemas.forms import ForwardForm, ResolveForm, ResponseForm, StatusForm, errors_of
from app.services import notifications as notif
from app.services import settings as cfg
from app.services import stats as stats_svc
from app.services.issues import (can_claim, can_manage, change_status, constituency_clause, issue_query,
                                 relevance_tier, sort_for_mp)
from app.services.uploads import UploadError, has_file, save_image
from app.templating import flash, render

router = APIRouter(prefix="/mp", dependencies=[Depends(require_mp)])

VIEWS = {
    "constituency": "📍 Миний тойргийн асуудлууд",
    "new": "🆕 Шинэ асуудлууд",
    "active": "🛠️ Шийдвэрлэж буй",
    "resolved": "✅ Шийдвэрлэсэн",
    "urgent": "⚡ Шуурхай анхаарах",
}
SORTS = {"relevance": "Тойргийн хамаарлаар", "priority": "Ач холбогдлоор", "support": "Дэмжлэгээр",
         "newest": "Шинэ нь эхэндээ"}


def _profile(db: Session, user: User) -> MPProfile | None:
    return db.scalar(select(MPProfile).where(MPProfile.user_id == user.id)
                     .options(selectinload(MPProfile.khoroos), joinedload(MPProfile.district)))


def _constituency_issues(db: Session, user: User, profile: MPProfile | None) -> list[Issue]:
    stmt = issue_query().options(selectinload(Issue.confirmations)).where(constituency_clause(profile, user.id))
    return list(db.scalars(stmt).unique())


def _is_urgent(issue: Issue, threshold: int) -> bool:
    if issue.is_resolved:
        return issue.confirmation_stats["disputed"]
    return issue.priority_score >= threshold or issue.urgency == "critical"


@router.get("")
def dashboard(request: Request, user: User = Depends(require_mp), db: Session = Depends(get_db)):
    profile = _profile(db, user)
    issues = _constituency_issues(db, user, profile)
    ordered = sort_for_mp(issues, profile, user.id)
    threshold = cfg.get_int(db, "high_priority_threshold")
    open_issues = [i for i in ordered if not i.is_resolved]
    urgent = sorted([i for i in ordered if _is_urgent(i, threshold)], key=lambda i: -i.priority_score)
    resolved = sorted([i for i in issues if i.is_resolved], key=lambda i: i.resolved_at, reverse=True)
    khoroo_bars = []
    if profile:
        for k in profile.khoroos:
            ks = [i for i in issues if i.khoroo_id == k.id]
            khoroo_bars.append({"label": k.label, "open": sum(1 for i in ks if not i.is_resolved),
                                "resolved": sum(1 for i in ks if i.is_resolved)})
    return render(request, "mp/dashboard.html", {
        "profile": profile, "stats": stats_svc.mp_stats(db, issues, user.id),
        "urgent": urgent[:5], "urgent_count": len(urgent),
        "constituency": open_issues[:8], "open_count": len(open_issues),
        "most_supported": sorted(issues, key=lambda i: -i.support_count)[:5],
        "top": sorted(open_issues, key=lambda i: (-i.priority_score, -i.support_count))[:5],
        "in_progress": [i for i in ordered if i.status in ACTIVE_STATUSES][:6],
        "resolved": resolved[:5], "khoroo_bars": khoroo_bars, "threshold": threshold,
        "khoroo_max": max([k["open"] + k["resolved"] for k in khoroo_bars] + [1]),
        "tier": lambda i: relevance_tier(i, profile, user.id),
    })


@router.get("/issues")
def mp_issues(request: Request, view: str = "constituency", q: str = "", category: str = "",
              sort: str = "relevance", user: User = Depends(require_mp), db: Session = Depends(get_db)):
    profile = _profile(db, user)
    issues = _constituency_issues(db, user, profile)
    threshold = cfg.get_int(db, "high_priority_threshold")
    if view not in VIEWS:
        view = "constituency"
    if view == "new":
        issues = [i for i in issues if i.status == "NEW"]
    elif view == "active":
        issues = [i for i in issues if i.status in ACTIVE_STATUSES]
    elif view == "resolved":
        issues = [i for i in issues if i.is_resolved]
    elif view == "urgent":
        issues = [i for i in issues if _is_urgent(i, threshold)]
    if category in CATEGORIES:
        issues = [i for i in issues if i.category == category]
    q = q.strip()[:100]
    if q:
        needle = q.lower()
        issues = [i for i in issues if needle in i.title.lower() or needle in i.description.lower()
                  or needle in (i.location or "").lower()]
    if sort == "priority":
        issues.sort(key=lambda i: -i.priority_score)
    elif sort == "support":
        issues.sort(key=lambda i: -i.support_count)
    elif sort == "newest":
        issues.sort(key=lambda i: i.created_at, reverse=True)
    else:
        sort = "relevance"
        issues = sort_for_mp(issues, profile, user.id)
    return render(request, "mp/issues.html", {
        "issues": issues, "view": view, "views": VIEWS, "sorts": SORTS, "sort": sort, "q": q,
        "category": category, "profile": profile, "threshold": threshold,
        "tier": lambda i: relevance_tier(i, profile, user.id),
    })


# ---------- Үйлдлүүд ----------
def _managed_issue(db: Session, issue_id: int, user: User, allow_claim: bool = False) -> Issue:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(404)
    if can_manage(issue, user) or (allow_claim and can_claim(issue, user)):
        return issue
    raise Forbidden("Энэ асуудал таны хариуцлагад хамаарахгүй байна. Хариуцах гишүүнийг админ өөрчилж болно.")


def _back(issue_id: int, anchor: str = "timeline") -> RedirectResponse:
    return RedirectResponse(f"/issues/{issue_id}#{anchor}", status_code=303)


@router.post("/issues/{issue_id}/accept")
def accept_issue(issue_id: int, request: Request, message: str = Form(""), user: User = Depends(require_mp),
                 db: Session = Depends(get_db)):
    issue = _managed_issue(db, issue_id, user, allow_claim=True)
    if issue.status != "NEW":
        flash(request, "Энэ асуудал аль хэдийн хүлээн авагдсан байна.", "info")
        return _back(issue_id)
    issue.mp_id = user.id
    change_status(db, issue, "RECEIVED", user, note="Асуудлыг хүлээн авлаа", notify_author=False)
    content = message.strip()[:2000] or ("Таны асуудлыг хүлээн авлаа. Холбогдох мэдээллийг судалж, "
                                         "ажлын 5 хоногт багтаан хариу өгнө.")
    db.add(OfficialResponse(issue_id=issue.id, author_id=user.id, kind="response", content=content))
    notif.on_received(db, issue, user)
    db.commit()
    flash(request, "Асуудлыг хүлээн авлаа. Иргэнд мэдэгдэл илгээгдлээ.")
    return _back(issue_id)


@router.post("/issues/{issue_id}/status")
def update_status(issue_id: int, request: Request, status: str = Form(""), note: str = Form(""),
                  user: User = Depends(require_mp), db: Session = Depends(get_db)):
    issue = _managed_issue(db, issue_id, user)
    try:
        data = StatusForm(status=status, note=note)
    except ValidationError as e:
        flash(request, errors_of(e)[0], "error")
        return _back(issue_id, "mp-panel")
    reopened = issue.is_resolved
    label = STATUS_INFO[data.status]["label"]
    changed = change_status(db, issue, data.status, user,
                            note=data.note or ("Асуудлыг дахин нээв" if reopened else f"Төлөв: {label}"))
    if not changed:
        flash(request, "Асуудал аль хэдийн энэ төлөвт байна.", "info")
        return _back(issue_id, "mp-panel")
    db.commit()
    flash(request, f"Төлөв шинэчлэгдлээ: {label}")
    return _back(issue_id)


@router.post("/issues/{issue_id}/response")
def add_response(issue_id: int, request: Request, content: str = Form(""), kind: str = Form("response"),
                 user: User = Depends(require_mp), db: Session = Depends(get_db)):
    issue = _managed_issue(db, issue_id, user)
    try:
        data = ResponseForm(content=content, kind=kind)
    except ValidationError as e:
        flash(request, errors_of(e)[0], "error")
        return _back(issue_id, "mp-panel")
    if issue.status == "NEW":
        change_status(db, issue, "RECEIVED", user, note="Асуудлыг хүлээн авлаа", notify_author=False)
    db.add(OfficialResponse(issue_id=issue.id, author_id=user.id, kind=data.kind, content=data.content))
    notif.on_response(db, issue, user)
    db.commit()
    flash(request, "Албан ёсны хариу нийтлэгдлээ." if data.kind == "response" else "Явцын мэдээлэл нийтлэгдлээ.")
    return _back(issue_id, "responses")


@router.post("/issues/{issue_id}/forward")
def forward_issue(issue_id: int, request: Request, organization: str = Form(""),
                  organization_other: str = Form(""), note: str = Form(""), user: User = Depends(require_mp),
                  db: Session = Depends(get_db)):
    issue = _managed_issue(db, issue_id, user)
    org = organization_other.strip() if organization == "__other__" else organization
    try:
        data = ForwardForm(organization=org, note=note)
    except ValidationError as e:
        flash(request, errors_of(e)[0], "error")
        return _back(issue_id, "mp-panel")
    issue.forwarded_to = data.organization
    content = data.note or ("Тус асуудлыг хүлээн авч, холбогдох байгууллагад албан бичгээр хүргүүлэн ажиллаж "
                            f"байна. Хүлээн авсан байгууллага: {data.organization}.")
    db.add(OfficialResponse(issue_id=issue.id, author_id=user.id, kind="forward", organization=data.organization,
                            content=content))
    if issue.status_index < STATUSES.index("FORWARDED"):
        change_status(db, issue, "FORWARDED", user, note=f"Хүлээн авсан байгууллага: {data.organization}",
                      notify_author=False)
    notif.on_response(db, issue, user)
    db.commit()
    flash(request, f"Асуудлыг \"{data.organization}\"-д шилжүүллээ.")
    return _back(issue_id)


@router.post("/issues/{issue_id}/resolve")
def resolve_issue(issue_id: int, request: Request, explanation: str = Form(""), action_taken: str = Form(""),
                  resolved_on: str = Form(""), official_response: str = Form(""),
                  before_image: UploadFile | None = File(None), after_image: UploadFile | None = File(None),
                  user: User = Depends(require_mp), db: Session = Depends(get_db)):
    issue = _managed_issue(db, issue_id, user)
    try:
        data = ResolveForm(explanation=explanation, action_taken=action_taken, resolved_on=resolved_on,
                           official_response=official_response)
    except ValidationError as e:
        flash(request, errors_of(e)[0], "error")
        return _back(issue_id, "mp-panel")
    if not has_file(after_image) and not issue.after_image:
        flash(request, "Шийдвэрлэсний дараах зургийг (нотлох баримт) заавал оруулна уу.", "error")
        return _back(issue_id, "mp-panel")
    try:
        before_path = save_image(before_image, "resolutions")
        after_path = save_image(after_image, "resolutions")
    except UploadError as e:
        flash(request, str(e), "error")
        return _back(issue_id, "mp-panel")
    res = db.scalar(select(Resolution).where(Resolution.issue_id == issue.id))
    if res is None:
        res = Resolution(issue_id=issue.id, explanation="", action_taken="", resolved_on=data.resolved_on)
        db.add(res)
    res.explanation = data.explanation
    res.action_taken = data.action_taken
    res.resolved_on = data.resolved_on
    res.official_response = data.official_response
    res.resolved_by_id = user.id
    if before_path:
        db.add(IssueImage(issue_id=issue.id, path=before_path, kind="before", uploaded_by_id=user.id))
    if after_path:
        db.add(IssueImage(issue_id=issue.id, path=after_path, kind="after", uploaded_by_id=user.id))
    db.add(OfficialResponse(issue_id=issue.id, author_id=user.id, kind="resolution",
                            content=data.official_response or data.explanation))
    for c in list(issue.confirmations):  # дахин шийдвэрлэсэн бол өмнөх баталгаажуулалтыг шинэчилнэ
        db.delete(c)
    change_status(db, issue, "RESOLVED", user, note="Асуудал шийдвэрлэгдлээ", notify_author=False)
    notif.on_resolved(db, issue)
    db.commit()
    flash(request, "🎉 Асуудлыг шийдвэрлэсэн гэж тэмдэглэлээ. Иргэд баталгаажуулах боломжтой боллоо.")
    return _back(issue_id, "resolution")


# ---------- Профайл ----------
@router.get("/profile")
def mp_profile(request: Request, user: User = Depends(require_mp), db: Session = Depends(get_db)):
    profile = _profile(db, user)
    issues = _constituency_issues(db, user, profile)
    return render(request, "mp/profile.html", {"profile": profile,
                                               "stats": stats_svc.mp_stats(db, issues, user.id)})


@router.post("/profile")
def mp_profile_update(request: Request, bio: str = Form(""), phone: str = Form(""),
                      profile_image: UploadFile | None = File(None), user: User = Depends(require_mp),
                      db: Session = Depends(get_db)):
    profile = _profile(db, user)
    if profile is None:
        profile = MPProfile(user_id=user.id)
        db.add(profile)
    profile.bio = bio.strip()[:2000]
    user.phone = phone.strip()[:32] or None
    try:
        path = save_image(profile_image, "profiles", max_side=600)
    except UploadError as e:
        flash(request, str(e), "error")
        return RedirectResponse("/mp/profile", status_code=303)
    if path:
        profile.profile_image = path
    db.commit()
    flash(request, "Профайл шинэчлэгдлээ.")
    return RedirectResponse("/mp/profile", status_code=303)
