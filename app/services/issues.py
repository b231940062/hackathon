"""Асуудлын үндсэн бизнес логик: ачаалах, төлөв солих, гишүүний тойрог, цагийн хэлхээс."""
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.constants import STATUS_INFO, STATUSES
from app.models import (Comment, District, Issue, IssueStatusHistory, MPProfile, OfficialResponse,
                        ResolutionConfirmation, Support, User)
from app.services import notifications as notif
from app.services.priority import compute_priority
from app.services.uploads import delete_image
from app.utils import utcnow


# ---------- Ачаалах ----------
def card_options():
    return (joinedload(Issue.district), joinedload(Issue.khoroo), joinedload(Issue.author),
            joinedload(Issue.mp), selectinload(Issue.images), selectinload(Issue.responses))


def issue_query():
    return select(Issue).options(*card_options())


def load_issue_full(db: Session, issue_id: int) -> Issue | None:
    stmt = (select(Issue).where(Issue.id == issue_id).options(
        joinedload(Issue.district), joinedload(Issue.khoroo), joinedload(Issue.author),
        joinedload(Issue.mp).joinedload(User.mp_profile),
        selectinload(Issue.images),
        selectinload(Issue.comments).joinedload(Comment.user),
        selectinload(Issue.history).joinedload(IssueStatusHistory.changed_by),
        selectinload(Issue.responses).joinedload(OfficialResponse.author),
        selectinload(Issue.confirmations).joinedload(ResolutionConfirmation.user),
        joinedload(Issue.resolution)))
    return db.scalars(stmt).unique().first()


def supported_ids(db: Session, user: User | None, issue_ids) -> set[int]:
    ids = list(issue_ids)
    if not user or not ids:
        return set()
    return set(db.scalars(select(Support.issue_id).where(Support.user_id == user.id, Support.issue_id.in_(ids))))


def districts_payload(db: Session) -> list[dict]:
    districts = db.scalars(select(District).options(selectinload(District.khoroos)).order_by(District.id)).all()
    return [{"id": d.id, "name": d.name, "lat": d.lat, "lng": d.lng,
             "khoroos": [{"id": k.id, "number": k.number, "lat": k.lat, "lng": k.lng} for k in d.khoroos]}
            for d in districts]


# ---------- Гишүүн ба тойрог ----------
def active_mp_profiles(db: Session) -> list[MPProfile]:
    stmt = (select(MPProfile).join(User, MPProfile.user_id == User.id)
            .where(User.role == "mp", User.is_active.is_(True))
            .options(selectinload(MPProfile.khoroos), joinedload(MPProfile.user), joinedload(MPProfile.district))
            .order_by(MPProfile.id))
    return list(db.scalars(stmt).unique())


def find_relevant_mp(db: Session, district_id: int | None, khoroo_id: int | None) -> User | None:
    """Эхлээд хороо нь оноогдсон гишүүн, дараа нь тухайн дүүргийн гишүүн."""
    profiles = active_mp_profiles(db)
    if khoroo_id:
        for p in profiles:
            if khoroo_id in p.khoroo_ids:
                return p.user
    if district_id:
        for p in profiles:
            if p.district_id == district_id:
                return p.user
    return None


def constituency_clause(profile: MPProfile | None, user_id: int):
    clauses = [Issue.mp_id == user_id]
    if profile is not None:
        if profile.district_id:
            clauses.append(Issue.district_id == profile.district_id)
        if profile.khoroo_ids:
            clauses.append(Issue.khoroo_id.in_(profile.khoroo_ids))
    return or_(*clauses)


def relevance_tier(issue: Issue, profile: MPProfile | None, user_id: int) -> int:
    """3: гишүүнд оноогдсон, 2: оноогдсон хороо, 1: тойргийн дүүрэг, 0: бусад."""
    tier = 0
    if profile is not None:
        if profile.district_id and issue.district_id == profile.district_id:
            tier = 1
        if issue.khoroo_id and issue.khoroo_id in profile.khoroo_ids:
            tier = 2
    if issue.mp_id == user_id:
        tier = max(tier, 2)
    return tier


def sort_for_mp(issues, profile: MPProfile | None, user_id: int) -> list[Issue]:
    # Тойргийн дүүрэг → оноогдсон хороо → их дэмжлэг → өндөр ач холбогдол
    return sorted(issues, key=lambda i: (-relevance_tier(i, profile, user_id), -i.support_count,
                                         -i.priority_score, -i.id))


def can_manage(issue: Issue, user: User | None) -> bool:
    return bool(user and user.is_mp and issue.mp_id == user.id)


def can_claim(issue: Issue, user: User | None) -> bool:
    return bool(user and user.is_mp and issue.mp_id is None and not issue.is_resolved)


# ---------- Өөрчлөлт ----------
def refresh_counts(db: Session, issue: Issue) -> None:
    db.flush()
    issue.support_count = db.scalar(select(func.count()).select_from(Support).where(Support.issue_id == issue.id))
    issue.comment_count = db.scalar(select(func.count()).select_from(Comment).where(
        Comment.issue_id == issue.id, Comment.is_hidden.is_(False)))
    issue.priority_score = compute_priority(issue)


def change_status(db: Session, issue: Issue, new_status: str, actor: User | None, note: str = "",
                  notify_author: bool = True, at=None) -> bool:
    if new_status not in STATUSES or new_status == issue.status:
        return False
    now = at or utcnow()
    db.add(IssueStatusHistory(issue_id=issue.id, old_status=issue.status, new_status=new_status,
                              changed_by_id=actor.id if actor else None, note=note[:500], created_at=now))
    issue.status = new_status
    issue.updated_at = now
    if new_status != "NEW" and issue.received_at is None:
        issue.received_at = now
    issue.resolved_at = now if new_status == "RESOLVED" else None
    issue.priority_score = compute_priority(issue)
    if notify_author and new_status not in ("RECEIVED", "RESOLVED"):
        notif.on_status(db, issue, STATUS_INFO[new_status]["label"])
    return True


def delete_issue(db: Session, issue: Issue) -> None:
    paths = [img.path for img in issue.images] + [c.image_path for c in issue.confirmations]
    db.delete(issue)
    db.flush()
    for p in paths:
        if p and p.startswith("uploads/") and "/seed/" not in p:
            delete_image(p)


def recompute_all_priorities(db: Session) -> None:
    for issue in db.scalars(select(Issue)):
        issue.priority_score = compute_priority(issue)
    db.commit()


# ---------- Харуулах ----------
def build_timeline(issue: Issue) -> list[dict]:
    reached = {"NEW": issue.created_at}
    for h in issue.history:
        reached[h.new_status] = h.created_at
    current = issue.status_index
    steps = []
    for i, status in enumerate(STATUSES):
        info = STATUS_INFO[status]
        if i < current:
            state = "done" if status in reached else "skipped"
        elif i == current:
            state = "done" if status == "RESOLVED" else "current"
        else:
            state = "upcoming"
        steps.append({"status": status, "label": info["label"], "short": info["short"], "icon": info["icon"],
                      "hint": info["hint"], "color": info["color"], "state": state,
                      "at": reached.get(status) if state in ("done", "current") else None})
    return steps


def build_activity(issue: Issue, include_comments: bool = False) -> list[dict]:
    events = []
    for h in issue.history:
        events.append({"type": "status", "at": h.created_at, "actor": h.changed_by, "status": h.new_status,
                       "old": h.old_status, "info": h.new_info, "note": h.note})
    for r in issue.responses:
        events.append({"type": "response", "at": r.created_at, "actor": r.author, "kind": r.kind,
                       "kind_label": r.kind_label, "content": r.content, "organization": r.organization})
    for c in issue.confirmations:
        events.append({"type": "confirmation", "at": c.created_at, "actor": c.user, "is_resolved": c.is_resolved,
                       "reason": c.reason})
    if include_comments:
        for c in issue.comments:
            events.append({"type": "comment", "at": c.created_at, "actor": c.user, "content": c.content,
                           "hidden": c.is_hidden, "id": c.id})
    events.sort(key=lambda e: e["at"])
    return events
