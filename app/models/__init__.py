"""Бүх ORM загварыг нэг дор импортолж, Base.metadata-д бүртгэнэ."""
from app.models.geo import District, Khoroo
from app.models.issue import (Comment, Issue, IssueImage, IssueStatusHistory, OfficialResponse, Resolution,
                              ResolutionConfirmation, Support)
from app.models.notification import Notification, Setting
from app.models.user import MPProfile, User, mp_khoroos

__all__ = [
    "District", "Khoroo", "User", "MPProfile", "mp_khoroos", "Issue", "IssueImage", "Comment", "Support",
    "OfficialResponse", "IssueStatusHistory", "Resolution", "ResolutionConfirmation", "Notification", "Setting",
]
