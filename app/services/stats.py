"""Статистик: нүүр хуудас, гишүүний самбар, админ тайлан."""
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.constants import ACTIVE_STATUSES, CATEGORIES, STATUSES
from app.models import District, Issue, MPProfile, ResolutionConfirmation, Support, User
from app.utils import local_today, to_local, utcnow


def platform_stats(db: Session) -> dict:
    by_status = dict(db.execute(select(Issue.status, func.count()).group_by(Issue.status)).all())
    total = sum(by_status.values())
    resolved = by_status.get("RESOLVED", 0)
    by_role = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    return {
        "total_issues": total,
        "new": by_status.get("NEW", 0),
        "active": sum(by_status.get(s, 0) for s in ACTIVE_STATUSES),
        "resolved": resolved,
        "resolved_pct": round(resolved * 100 / total) if total else 0,
        "supports": db.scalar(select(func.count()).select_from(Support)) or 0,
        "users": sum(by_role.values()),
        "citizens": by_role.get("citizen", 0),
        "mps": by_role.get("mp", 0),
        "admins": by_role.get("admin", 0),
        "by_status": {s: by_status.get(s, 0) for s in STATUSES},
    }


def _avg_hours(pairs) -> float | None:
    vals = [(b - a).total_seconds() / 3600 for a, b in pairs if a and b and b >= a]
    return round(sum(vals) / len(vals), 1) if vals else None


def format_duration(hours: float | None) -> str:
    if hours is None:
        return "—"
    if hours < 24:
        return f"{hours:.0f} цаг"
    return f"{hours / 24:.1f} хоног"


def mp_stats(db: Session, issues: list[Issue], mp_user_id: int) -> dict:
    """Гишүүний тойргийн асуудлуудын жагсаалтаас гүйцэтгэлийн үзүүлэлт тооцно."""
    mine = [i for i in issues if i.mp_id == mp_user_id]
    resolved = [i for i in issues if i.status == "RESOLVED"]
    confirmations = db.execute(
        select(ResolutionConfirmation.is_resolved, func.count())
        .join(Issue, Issue.id == ResolutionConfirmation.issue_id)
        .where(Issue.mp_id == mp_user_id).group_by(ResolutionConfirmation.is_resolved)).all()
    conf = {bool(k): v for k, v in confirmations}
    conf_total = conf.get(True, 0) + conf.get(False, 0)
    return {
        "total": len(issues),
        "new": sum(1 for i in issues if i.status == "NEW"),
        "active": sum(1 for i in issues if i.status in ACTIVE_STATUSES),
        "resolved": len(resolved),
        "assigned": len(mine),
        "resolved_pct": round(len(resolved) * 100 / len(issues)) if issues else 0,
        "avg_response": format_duration(_avg_hours((i.created_at, i.received_at) for i in mine)),
        "avg_resolution": format_duration(_avg_hours((i.created_at, i.resolved_at) for i in mine)),
        "satisfaction": round(conf.get(True, 0) * 100 / conf_total) if conf_total else None,
        "confirmations": conf_total,
    }


def district_breakdown(db: Session) -> list[dict]:
    rows = db.execute(select(District.id, District.name, District.lat, District.lng, Issue.status,
                             func.count(Issue.id))
                      .join(Issue, Issue.district_id == District.id, isouter=True)
                      .group_by(District.id, District.name, District.lat, District.lng, Issue.status)).all()
    data: dict = {}
    for did, name, lat, lng, status, count in rows:
        d = data.setdefault(did, {"id": did, "name": name, "lat": lat, "lng": lng, "total": 0, "resolved": 0,
                                  "active": 0, "new": 0})
        if status:
            d["total"] += count
            if status == "RESOLVED":
                d["resolved"] += count
            elif status == "NEW":
                d["new"] += count
            else:
                d["active"] += count
    out = sorted(data.values(), key=lambda d: -d["total"])
    for d in out:
        d["resolved_pct"] = round(d["resolved"] * 100 / d["total"]) if d["total"] else 0
    return out


def category_breakdown(db: Session) -> list[dict]:
    rows = db.execute(select(Issue.category, Issue.status, func.count()).group_by(Issue.category, Issue.status)).all()
    agg: dict = defaultdict(lambda: {"total": 0, "resolved": 0})
    for cat, status, count in rows:
        agg[cat]["total"] += count
        if status == "RESOLVED":
            agg[cat]["resolved"] += count
    out = []
    for cat, v in agg.items():
        info = CATEGORIES.get(cat, CATEGORIES["other"])
        out.append({"key": cat, "label": info["label"], "icon": info["icon"], "color": info["color"], **v,
                    "resolved_pct": round(v["resolved"] * 100 / v["total"]) if v["total"] else 0})
    return sorted(out, key=lambda d: -d["total"])


def weekly_counts(db: Session, weeks: int = 10) -> list[dict]:
    """Долоо хоног бүрээр: шинээр мэдээлэгдсэн ба шийдвэрлэгдсэн асуудлын тоо."""
    today = local_today()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)  # эхний долоо хоногийн Даваа
    since = utcnow() - timedelta(weeks=weeks + 1)
    created = db.scalars(select(Issue.created_at).where(Issue.created_at >= since)).all()
    resolved = db.scalars(select(Issue.resolved_at).where(Issue.resolved_at.is_not(None),
                                                          Issue.resolved_at >= since)).all()
    buckets = []
    for w in range(weeks):
        ws = start + timedelta(weeks=w)
        buckets.append({"start": ws, "label": ws.strftime("%m.%d"), "created": 0, "resolved": 0})
    for key, values in (("created", created), ("resolved", resolved)):
        for dt in values:
            idx = (to_local(dt).date() - start).days // 7
            if 0 <= idx < weeks:
                buckets[idx][key] += 1
    for b in buckets:
        end = b["start"] + timedelta(days=6)
        b["tip"] = (f"{b['start'].strftime('%m.%d')}–{end.strftime('%m.%d')}: мэдээлэгдсэн {b['created']}, "
                    f"шийдвэрлэгдсэн {b['resolved']}")
    return buckets


def mp_performance(db: Session) -> list[dict]:
    profiles = db.scalars(select(MPProfile).join(User, User.id == MPProfile.user_id)
                          .where(User.role == "mp")).all()
    out = []
    for p in profiles:
        issues = db.scalars(select(Issue).where(Issue.mp_id == p.user_id)).all()
        s = mp_stats(db, issues, p.user_id)
        out.append({"profile": p, "user": p.user, **s})
    return sorted(out, key=lambda d: (-d["resolved"], -d["total"]))
