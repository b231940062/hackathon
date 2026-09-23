"""Нүүр хуудас, газрын зураг, гишүүдийн нийтийн профайл, туслах API."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth.deps import get_current_user
from app.constants import STATUS_INFO
from app.database import get_db
from app.models import Issue, MPProfile, User
from app.services import settings as cfg
from app.services import stats as stats_svc
from app.services.duplicates import find_similar
from app.services.issues import (active_mp_profiles, constituency_clause, find_relevant_mp, issue_query,
                                 sort_for_mp, supported_ids)
from app.templating import render
from app.utils import parse_int

router = APIRouter()


@router.get("/")
def home(request: Request, user: User | None = Depends(get_current_user), db: Session = Depends(get_db)):
    top = db.scalars(issue_query().where(Issue.status != "RESOLVED")
                     .order_by(Issue.priority_score.desc(), Issue.support_count.desc()).limit(6)).unique().all()
    recent = db.scalars(issue_query().order_by(Issue.created_at.desc()).limit(6)).unique().all()
    resolved = db.scalars(issue_query().where(Issue.status == "RESOLVED")
                          .order_by(Issue.resolved_at.desc()).limit(4)).unique().all()
    ids = {i.id for i in top + recent + resolved}
    return render(request, "home.html", {
        "stats": stats_svc.platform_stats(db), "top_issues": top, "recent_issues": recent,
        "resolved_issues": resolved, "supported": supported_ids(db, user, ids),
        "mp_count": len(active_mp_profiles(db)),
    })


@router.get("/map")
def issue_map(request: Request, db: Session = Depends(get_db)):
    issues = db.scalars(select(Issue).options(joinedload(Issue.district), joinedload(Issue.khoroo))
                        .where(Issue.lat.is_not(None)).order_by(Issue.created_at.desc()).limit(800)).unique().all()
    markers = [{
        "id": i.id, "title": i.title, "status": i.status, "status_label": STATUS_INFO[i.status]["label"],
        "color": STATUS_INFO[i.status]["color"], "support": i.support_count, "priority": i.priority_score,
        "icon": i.category_info["icon"], "category": i.category, "location": i.location_label,
        "district_id": i.district_id, "lat": i.lat, "lng": i.lng,
    } for i in issues]
    return render(request, "issues/map.html", {"markers": markers,
                                               "districts": stats_svc.district_breakdown(db)})


@router.get("/mps")
def mp_list(request: Request, db: Session = Depends(get_db)):
    cards = []
    for p in active_mp_profiles(db):
        issues = db.scalars(select(Issue).where(constituency_clause(p, p.user_id))).all()
        cards.append({"profile": p, "user": p.user, "stats": stats_svc.mp_stats(db, issues, p.user_id)})
    return render(request, "mps/list.html", {"cards": cards})


@router.get("/mps/{user_id}")
def mp_public(user_id: int, request: Request, user: User | None = Depends(get_current_user),
              db: Session = Depends(get_db)):
    mp = db.scalar(select(User).where(User.id == user_id, User.role == "mp")
                   .options(joinedload(User.mp_profile).selectinload(MPProfile.khoroos)))
    if mp is None:
        raise HTTPException(404)
    profile = mp.mp_profile
    issues = db.scalars(issue_query().where(constituency_clause(profile, mp.id))).unique().all()
    ordered = sort_for_mp(issues, profile, mp.id)
    return render(request, "mps/detail.html", {
        "mp": mp, "profile": profile, "stats": stats_svc.mp_stats(db, issues, mp.id),
        "active": [i for i in ordered if i.status != "RESOLVED"][:8],
        "resolved": [i for i in ordered if i.status == "RESOLVED"][:6],
        "supported": supported_ids(db, user, [i.id for i in issues]),
    })


# ---------- JSON туслах API ----------
@router.get("/api/issues/similar")
def api_similar(request: Request, title: str = "", district_id: str = "", khoroo_id: str = "", category: str = "",
                exclude: str = "", user: User | None = Depends(get_current_user), db: Session = Depends(get_db)):
    title = title.strip()[:150]
    if len(title) < 4:
        return {"results": []}
    matches = find_similar(db, title, parse_int(district_id), parse_int(khoroo_id), category or None,
                           exclude_id=parse_int(exclude), threshold=cfg.get_float(db, "duplicate_threshold"))
    mine = supported_ids(db, user, [i.id for i, _ in matches])
    return {"results": [{
        "id": i.id, "title": i.title, "status_label": STATUS_INFO[i.status]["label"],
        "status_color": STATUS_INFO[i.status]["color"], "support_count": i.support_count,
        "location": i.location_label, "score": round(score * 100), "url": f"/issues/{i.id}",
        "supported": i.id in mine, "is_author": bool(user and i.author_id == user.id),
    } for i, score in matches]}


@router.get("/api/relevant-mp")
def api_relevant_mp(district_id: str = "", khoroo_id: str = "", db: Session = Depends(get_db)):
    mp = find_relevant_mp(db, parse_int(district_id), parse_int(khoroo_id))
    if mp is None:
        return {"mp": None}
    p = db.scalar(select(MPProfile).where(MPProfile.user_id == mp.id).options(selectinload(MPProfile.khoroos)))
    return {"mp": {"id": mp.id, "name": mp.full_name, "initials": mp.initials, "color": mp.avatar_color,
                   "position": p.position if p else "", "constituency": p.constituency if p else "",
                   "image": ("/static/" + p.profile_image) if p and p.profile_image else None,
                   "url": f"/mps/{mp.id}"}}
