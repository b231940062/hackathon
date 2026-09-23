"""Иргэдийн талын асуудлын урсгал: мэдээ, мэдээлэх, дэлгэрэнгүй, дэмжих, сэтгэгдэл, баталгаажуулах."""
import random
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, login_required, require_citizen
from app.constants import CATEGORIES, STATUSES
from app.database import ci_contains, get_db
from app.models import (Comment, District, Issue, IssueImage, IssueStatusHistory, Khoroo, ResolutionConfirmation,
                        Support, User)
from app.schemas.forms import CommentForm, ConfirmForm, IssueForm, errors_of
from app.seed import CATEGORY_COMMENTS, GENERIC_COMMENTS
from app.services import notifications as notif
from app.services import ratelimit
from app.services import settings as cfg
from app.services import stats as stats_svc
from app.services.duplicates import find_similar
from app.services.issues import (build_activity, build_timeline, can_claim, can_manage, districts_payload,
                                 find_relevant_mp, issue_query, load_issue_full, refresh_counts, supported_ids)
from app.services.priority import priority_breakdown
from app.services.uploads import UploadError, save_image
from app.templating import flash, render
from app.utils import parse_int, safe_next

router = APIRouter()

PAGE_SIZE = 8
FEED_TABS = [("new", "🕒 Шинэ"), ("top", "🔥 Топ асуудлууд"), ("support", "👍 Их дэмжигдсэн"),
             ("resolved", "✅ Шийдвэрлэсэн")]


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


def _error(request: Request, message: str, status: int, back: str):
    if wants_json(request):
        return JSONResponse({"error": message}, status_code=status)
    flash(request, message, "error")
    return RedirectResponse(back, status_code=303)


def referer_path(request: Request, default: str) -> str:
    """JS-гүй үед өмнөх хуудас руу буцаах (зөвхөн ижил домэйн доторх зам)."""
    ref = urlparse(request.headers.get("referer", ""))
    if ref.netloc and ref.netloc != request.url.netloc:
        return default
    path = ref.path + (f"?{ref.query}" if ref.query else "")
    return safe_next(path, default)


def _get_issue(db: Session, issue_id: int) -> Issue:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(404)
    return issue


@router.get("/issues")
def feed(request: Request, tab: str = "new", q: str = "", category: str = "", district: str = "",
         status: str = "", page: int = 1, partial: int = 0, user: User | None = Depends(get_current_user),
         db: Session = Depends(get_db)):
    q = q.strip()[:100]
    page = max(1, min(page, 500))
    stmt = issue_query()
    if q:
        stmt = stmt.where(or_(ci_contains(Issue.title, q), ci_contains(Issue.description, q),
                              ci_contains(Issue.location, q)))
    if category in CATEGORIES:
        stmt = stmt.where(Issue.category == category)
    district_id = parse_int(district)
    if district_id:
        stmt = stmt.where(Issue.district_id == district_id)
    if status in STATUSES:
        stmt = stmt.where(Issue.status == status)
    elif status == "open":
        stmt = stmt.where(Issue.status != "RESOLVED")

    if tab == "top":
        stmt = stmt.where(Issue.status != "RESOLVED").order_by(Issue.priority_score.desc(),
                                                               Issue.support_count.desc())
    elif tab == "support":
        stmt = stmt.order_by(Issue.support_count.desc(), Issue.created_at.desc())
    elif tab == "resolved":
        stmt = stmt.where(Issue.status == "RESOLVED").order_by(Issue.resolved_at.desc())
    else:
        tab = "new"
        stmt = stmt.order_by(Issue.created_at.desc())

    rows = db.scalars(stmt.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE + 1)).unique().all()
    has_more = len(rows) > PAGE_SIZE
    issues = rows[:PAGE_SIZE]
    ctx = {"issues": issues, "supported": supported_ids(db, user, [i.id for i in issues]), "has_more": has_more,
           "page": page, "tab": tab, "q": q, "category": category, "district": district_id or "", "status": status}
    if partial:
        return render(request, "issues/_cards.html", ctx)

    top5 = db.scalars(issue_query().where(Issue.status != "RESOLVED")
                      .order_by(Issue.priority_score.desc()).limit(5)).unique().all()
    recent_resolved = db.scalars(issue_query().where(Issue.status == "RESOLVED")
                                 .order_by(Issue.resolved_at.desc()).limit(3)).unique().all()
    my_mp = None
    if user and user.is_citizen and user.district_id:
        my_mp = find_relevant_mp(db, user.district_id, user.khoroo_id)
    cat_counts = dict(db.execute(select(Issue.category, func.count()).group_by(Issue.category)).all())
    ctx.update({
        "tabs": FEED_TABS, "top5": top5, "recent_resolved": recent_resolved, "my_mp": my_mp,
        "stats": stats_svc.platform_stats(db), "cat_counts": cat_counts,
        "districts": db.scalars(select(District).order_by(District.id)).all(),
    })
    return render(request, "issues/feed.html", ctx)


@router.get("/issues/new")
def new_issue_page(request: Request, title: str = "", user: User = Depends(require_citizen),
                   db: Session = Depends(get_db)):
    form = {"title": title[:150], "district_id": user.district_id or "", "khoroo_id": user.khoroo_id or "",
            "urgency": "medium", "affected_scope": "street", "category": ""}
    return render(request, "issues/new.html", {"districts": districts_payload(db), "form": form})


@router.post("/issues/new")
def create_issue(request: Request, title: str = Form(""), description: str = Form(""), category: str = Form(""),
                 district_id: str = Form(""), khoroo_id: str = Form(""), location: str = Form(""),
                 urgency: str = Form("medium"), affected_scope: str = Form("street"), lat: str = Form(""),
                 lng: str = Form(""), dup_checked: str = Form(""), image: UploadFile | None = File(None),
                 user: User = Depends(require_citizen), db: Session = Depends(get_db)):
    raw = {"title": title, "description": description, "category": category, "district_id": parse_int(district_id),
           "khoroo_id": parse_int(khoroo_id), "location": location, "urgency": urgency,
           "affected_scope": affected_scope, "lat": lat, "lng": lng}
    ctx = {"districts": districts_payload(db), "form": raw}

    def fail(errors, duplicates=None, status=400):
        return render(request, "issues/new.html", {**ctx, "errors": errors, "duplicates": duplicates or []},
                      status_code=status)

    if not ratelimit.allow(f"issue:{user.id}", limit=10, window_seconds=3600):
        return fail(["Та цагт 10-аас олон асуудал мэдээлэх боломжгүй. Түр хүлээнэ үү."], status=429)
    try:
        data = IssueForm(**raw)
    except ValidationError as e:
        return fail(errors_of(e))
    district = db.get(District, data.district_id)
    if district is None:
        return fail(["Дүүрэг буруу сонгогдсон байна."])
    khoroo = db.get(Khoroo, data.khoroo_id) if data.khoroo_id else None
    if data.khoroo_id and (khoroo is None or khoroo.district_id != district.id):
        return fail(["Хороо буруу сонгогдсон байна."])

    if dup_checked != "1":
        threshold = max(0.75, cfg.get_float(db, "duplicate_threshold"))
        dups = find_similar(db, data.title, district.id, data.khoroo_id, data.category, threshold=threshold)
        if dups:
            return fail(["Энэ асуудал өмнө нь мэдээлэгдсэн байж магадгүй. Доорх асуудлыг дэмжих эсвэл "
                         "шинээр үргэлжлүүлнэ үү. (Зургаа дахин сонгох шаардлагатай)"],
                        duplicates=[i for i, _ in dups], status=409)
    try:
        image_path = save_image(image, "issues")
    except UploadError as e:
        return fail([str(e)])

    lat_v, lng_v = data.lat, data.lng
    if lat_v is None:
        base = khoroo or district
        rng = random.Random()
        lat_v = round(base.lat + rng.uniform(-0.003, 0.003), 5)
        lng_v = round(base.lng + rng.uniform(-0.004, 0.004), 5)
    mp = find_relevant_mp(db, district.id, data.khoroo_id)
    issue = Issue(title=data.title, description=data.description, category=data.category, district_id=district.id,
                  khoroo_id=data.khoroo_id, location=data.location, urgency=data.urgency,
                  affected_scope=data.affected_scope, lat=lat_v, lng=lng_v, author_id=user.id,
                  mp_id=mp.id if mp else None)
    db.add(issue)
    db.flush()
    if image_path:
        db.add(IssueImage(issue_id=issue.id, path=image_path, kind="original", uploaded_by_id=user.id))
    db.add(IssueStatusHistory(issue_id=issue.id, old_status=None, new_status="NEW", changed_by_id=user.id,
                              note="Иргэн асуудлыг мэдээллээ"))
    db.add(Support(issue_id=issue.id, user_id=user.id))
    refresh_counts(db, issue)
    notif.on_new_issue(db, issue)
    db.commit()
    who = f" Хариуцах гишүүн: {mp.full_name}." if mp else ""
    flash(request, f"Таны асуудал амжилттай бүртгэгдлээ!{who} Иргэдээс дэмжлэг цуглуулахын тулд холбоосоо хуваалцаарай.")
    return RedirectResponse(f"/issues/{issue.id}", status_code=303)


@router.get("/issues/{issue_id}")
def issue_detail(issue_id: int, request: Request, user: User | None = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    issue = load_issue_full(db, issue_id)
    if issue is None:
        raise HTTPException(404)
    my_conf = None
    if user:
        my_conf = next((c for c in issue.confirmations if c.user_id == user.id), None)
    similar = [i for i, _ in find_similar(db, issue.title, issue.district_id, issue.khoroo_id, issue.category,
                                          exclude_id=issue.id, threshold=0.45, limit=3)]
    return render(request, "issues/detail.html", {
        "issue": issue, "timeline": build_timeline(issue), "activity": build_activity(issue),
        "breakdown": priority_breakdown(issue), "supported": bool(supported_ids(db, user, [issue.id])),
        "my_conf": my_conf, "can_manage": can_manage(issue, user), "can_claim": can_claim(issue, user),
        "mp_profile": issue.mp.mp_profile if issue.mp else None, "similar": similar,
        "conf": issue.confirmation_stats,
        "is_author": bool(user and issue.author_id == user.id),
    })


@router.post("/issues/{issue_id}/support")
def toggle_support(issue_id: int, request: Request, user: User = Depends(login_required),
                   db: Session = Depends(get_db)):
    back = f"/issues/{issue_id}"
    if not user.is_citizen:
        return _error(request, "Зөвхөн иргэд асуудлыг дэмжих боломжтой.", 403, back)
    if not ratelimit.allow(f"support:{user.id}", limit=60, window_seconds=60):
        return _error(request, "Хэт олон үйлдэл. Түр хүлээнэ үү.", 429, back)
    issue = _get_issue(db, issue_id)
    if issue.author_id == user.id:
        return _error(request, "Та өөрийн мэдээлсэн асуудлыг аль хэдийн дэмжсэн байна.", 400, back)
    existing = db.scalar(select(Support).where(Support.issue_id == issue.id, Support.user_id == user.id))
    if existing:
        db.delete(existing)
        supported = False
    else:
        db.add(Support(issue_id=issue.id, user_id=user.id))
        supported = True
    try:
        refresh_counts(db, issue)
    except IntegrityError:  # давхар даралт — нэг иргэн нэг л удаа дэмжинэ
        db.rollback()
        issue = _get_issue(db, issue_id)
        supported = True
    if supported:
        notif.on_support(db, issue, user)
    db.commit()
    if wants_json(request):
        return {"supported": supported, "count": issue.support_count, "priority": issue.priority_score}
    flash(request, "Та энэ асуудлыг дэмжлээ. Баярлалаа!" if supported else "Дэмжлэгээ цуцаллаа.", "success")
    return RedirectResponse(referer_path(request, back), status_code=303)


@router.post("/issues/{issue_id}/comments")
def add_comment(issue_id: int, request: Request, content: str = Form(""), user: User = Depends(login_required),
                db: Session = Depends(get_db)):
    back = f"/issues/{issue_id}#comments"
    if not ratelimit.allow(f"comment:{user.id}", limit=10, window_seconds=60):
        return _error(request, "Хэт олон сэтгэгдэл. Түр хүлээнэ үү.", 429, back)
    try:
        data = CommentForm(content=content)
    except ValidationError as e:
        return _error(request, errors_of(e)[0], 400, back)
    issue = _get_issue(db, issue_id)
    comment = Comment(issue_id=issue.id, user_id=user.id, content=data.content)
    db.add(comment)
    refresh_counts(db, issue)
    notif.on_comment(db, issue, user)
    db.commit()
    if wants_json(request):
        return {"id": comment.id, "content": comment.content, "user_name": user.full_name,
                "initials": user.initials, "color": user.avatar_color, "role": user.role,
                "role_label": user.role_label, "time": "дөнгөж сая", "count": issue.comment_count}
    flash(request, "Сэтгэгдэл нэмэгдлээ.")
    return RedirectResponse(back, status_code=303)


@router.post("/issues/{issue_id}/confirm")
def confirm_resolution(issue_id: int, request: Request, answer: str = Form(""), reason: str = Form(""),
                       image: UploadFile | None = File(None), user: User = Depends(require_citizen),
                       db: Session = Depends(get_db)):
    back = f"/issues/{issue_id}#resolution"
    issue = _get_issue(db, issue_id)
    if not issue.is_resolved:
        return _error(request, "Энэ асуудал шийдвэрлэгдсэн төлөвт ороогүй байна.", 400, back)
    try:
        data = ConfirmForm(answer=answer, reason=reason)
    except ValidationError as e:
        return _error(request, errors_of(e)[0], 400, back)
    image_path = None
    if data.answer == "no":
        try:
            image_path = save_image(image, "followups")
        except UploadError as e:
            return _error(request, str(e), 400, back)
    conf = db.scalar(select(ResolutionConfirmation).where(ResolutionConfirmation.issue_id == issue.id,
                                                          ResolutionConfirmation.user_id == user.id))
    if conf is None:
        conf = ResolutionConfirmation(issue_id=issue.id, user_id=user.id, is_resolved=True)
        db.add(conf)
    conf.is_resolved = data.answer == "yes"
    conf.reason = data.reason if data.answer == "no" else ""
    if image_path:
        conf.image_path = image_path
        db.add(IssueImage(issue_id=issue.id, path=image_path, kind="followup", uploaded_by_id=user.id))
    if data.answer == "no":
        notif.on_dispute(db, issue, user)
    db.commit()
    if data.answer == "yes":
        flash(request, "Баталгаажуулсанд баярлалаа! Таны хариу шийдвэрлэлтийн ил тод байдлыг нэмэгдүүлнэ.")
    else:
        flash(request, "Таны мэдээллийг хүлээн авлаа. Хариуцсан гишүүнд мэдэгдэл илгээгдлээ.", "info")
    return RedirectResponse(back, status_code=303)


@router.post("/issues/{issue_id}/demo-boost")
def demo_boost(issue_id: int, request: Request, user: User = Depends(login_required), db: Session = Depends(get_db)):
    """Демо горим: олон иргэн дэмжиж буйг симуляци хийнэ (амьд үзүүлэнгийн үед)."""
    if not cfg.get_bool(db, "demo_mode"):
        raise HTTPException(404)
    issue = _get_issue(db, issue_id)
    have = set(db.scalars(select(Support.user_id).where(Support.issue_id == issue.id)))
    pool = [u for u in db.scalars(select(User).where(User.role == "citizen", User.is_active.is_(True),
                                                     User.email.like("%@demo.holboos.mn"))) if u.id not in have]
    rng = random.Random()
    for u in rng.sample(pool, min(30, len(pool))):
        db.add(Support(issue_id=issue.id, user_id=u.id))
    named = [u for u in db.scalars(select(User).where(User.role == "citizen", User.is_active.is_(True),
                                                      User.email.like("%@holboos.mn")))
             if u.id != issue.author_id]
    texts = CATEGORY_COMMENTS.get(issue.category, []) + GENERIC_COMMENTS
    added = 0
    for u, text in zip(rng.sample(named, min(3, len(named))), rng.sample(texts, min(3, len(texts)))):
        db.add(Comment(issue_id=issue.id, user_id=u.id, content=text))
        added += 1
    refresh_counts(db, issue)
    if issue.author_id:
        notif.notify(db, issue.author_id, "support",
                     f"Таны \"{issue.title}\" асуудлыг {issue.support_count} иргэн дэмжиж байна.", issue.id,
                     dedupe=True)
    notif.check_support_threshold(db, issue)
    threshold = cfg.get_int(db, "high_priority_threshold")
    if issue.mp_id and issue.priority_score >= threshold and not issue.is_resolved:
        notif.notify(db, issue.mp_id, "high_priority",
                     f"Таны тойргийн \"{issue.title}\" асуудлын ач холбогдол {issue.priority_score}/100 болж өслөө.",
                     issue.id, dedupe=True)
    db.commit()
    return {"count": issue.support_count, "comments": issue.comment_count, "priority": issue.priority_score,
            "added_comments": added}
