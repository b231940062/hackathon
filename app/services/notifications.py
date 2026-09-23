"""Мэдэгдэл үүсгэх үйл явдлууд (иргэн ба гишүүнд)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Issue, Notification, Support, User
from app.services import settings as cfg
from app.utils import utcnow


def notify(db: Session, user_id: int | None, kind: str, message: str, issue_id: int | None = None,
           dedupe: bool = False) -> None:
    if not user_id:
        return
    if dedupe:
        existing = db.scalar(select(Notification).where(
            Notification.user_id == user_id, Notification.issue_id == issue_id,
            Notification.kind == kind, Notification.is_read.is_(False)))
        if existing is not None:
            existing.message = message[:300]
            existing.created_at = utcnow()
            return
    db.add(Notification(user_id=user_id, issue_id=issue_id, kind=kind, message=message[:300]))
    db.flush()  # autoflush унтраастай тул дараагийн dedupe шалгалтад харагдуулна


def _short(issue: Issue) -> str:
    return issue.title if len(issue.title) <= 60 else issue.title[:57] + "…"


def on_support(db: Session, issue: Issue, supporter: User) -> None:
    if issue.author_id and issue.author_id != supporter.id:
        notify(db, issue.author_id, "support",
               f"Таны \"{_short(issue)}\" асуудлыг {issue.support_count} иргэн дэмжиж байна.",
               issue.id, dedupe=True)
    check_support_threshold(db, issue)


def check_support_threshold(db: Session, issue: Issue) -> None:
    threshold = cfg.get_int(db, "high_support_threshold")
    if issue.mp_id and issue.support_count >= threshold and not issue.is_resolved:
        already = db.scalar(select(Notification.id).where(
            Notification.user_id == issue.mp_id, Notification.issue_id == issue.id,
            Notification.kind == "high_support"))
        if already is None:
            notify(db, issue.mp_id, "high_support",
                   f"Таны тойргийн \"{_short(issue)}\" асуудал {issue.support_count}+ иргэний дэмжлэг авлаа.",
                   issue.id)


def on_comment(db: Session, issue: Issue, commenter: User) -> None:
    if issue.author_id and issue.author_id != commenter.id:
        notify(db, issue.author_id, "comment",
               f"{commenter.full_name} таны \"{_short(issue)}\" асуудалд сэтгэгдэл үлдээлээ.", issue.id, dedupe=True)
    if issue.mp_id and issue.mp_id != commenter.id and commenter.is_citizen:
        notify(db, issue.mp_id, "comment",
               f"Иргэн {commenter.full_name} \"{_short(issue)}\" асуудалд сэтгэгдэл бичлээ.", issue.id, dedupe=True)


def on_new_issue(db: Session, issue: Issue) -> None:
    threshold = cfg.get_int(db, "high_priority_threshold")
    if issue.mp_id and (issue.priority_score >= threshold or issue.urgency == "critical"):
        notify(db, issue.mp_id, "high_priority",
               f"Таны тойрогт өндөр ач холбогдолтой шинэ асуудал: \"{_short(issue)}\" "
               f"({issue.priority_score}/100).", issue.id)
    elif issue.mp_id:
        notify(db, issue.mp_id, "system", f"Таны тойрогт шинэ асуудал мэдээлэгдлээ: \"{_short(issue)}\".",
               issue.id)


def on_received(db: Session, issue: Issue, mp: User) -> None:
    notify(db, issue.author_id, "received",
           f"УИХ-ын гишүүн {mp.full_name} таны \"{_short(issue)}\" асуудлыг хүлээн авлаа.", issue.id)


def on_status(db: Session, issue: Issue, label: str) -> None:
    notify(db, issue.author_id, "status", f"\"{_short(issue)}\" асуудлын төлөв: {label}.", issue.id)


def on_response(db: Session, issue: Issue, mp: User) -> None:
    notify(db, issue.author_id, "response",
           f"{mp.full_name} таны \"{_short(issue)}\" асуудалд албан ёсны хариу өглөө.", issue.id)


def on_resolved(db: Session, issue: Issue) -> None:
    notify(db, issue.author_id, "resolved",
           f"🎉 Таны \"{_short(issue)}\" асуудал шийдвэрлэгдлээ. Бодитоор шийдэгдсэн эсэхийг баталгаажуулна уу.",
           issue.id)
    supporter_ids = db.scalars(select(Support.user_id).where(Support.issue_id == issue.id)).all()
    for uid in supporter_ids:
        if uid != issue.author_id:
            notify(db, uid, "resolved", f"Таны дэмжсэн \"{_short(issue)}\" асуудал шийдвэрлэгдлээ.", issue.id)


def on_dispute(db: Session, issue: Issue, citizen: User) -> None:
    notify(db, issue.mp_id, "dispute",
           f"Иргэн {citizen.full_name} \"{_short(issue)}\" асуудал бүрэн шийдэгдээгүй гэж мэдэгдлээ.", issue.id)
