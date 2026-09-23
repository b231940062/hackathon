"""Энгийн, ойлгомжтой ач холбогдлын оноо (0–100).

  Дэмжлэг        45 оноо  (логарифм, ~40 дэмжигчид дүүрнэ)
  Сэтгэгдэл      15 оноо  (логарифм, ~15 сэтгэгдэлд дүүрнэ)
  Хугацаа        10 оноо  (шийдэгдээгүй 30 хоногт дүүрнэ)
  Яаралтай байдал 20 оноо  (иргэний сонголт)
  Нөлөөллийн хүрээ 10 оноо (айл өрх → дүүрэг)
"""
import math

from app.constants import SCOPES, URGENCY
from app.utils import utcnow

W_SUPPORT, W_COMMENT, W_AGE = 45, 15, 10
SUPPORT_SATURATION, COMMENT_SATURATION, AGE_SATURATION_DAYS = 40, 15, 30

PRIORITY_LEVELS = [
    (75, "critical", "Маш өндөр"),
    (55, "high", "Өндөр"),
    (35, "medium", "Дунд"),
    (0, "low", "Бага"),
]


def priority_breakdown(issue, now=None) -> dict:
    now = now or utcnow()
    end = issue.resolved_at or now
    age_days = max(0.0, (end - issue.created_at).total_seconds() / 86400) if issue.created_at else 0.0
    parts = {
        "support": W_SUPPORT * min(1.0, math.log1p(issue.support_count or 0) / math.log1p(SUPPORT_SATURATION)),
        "comment": W_COMMENT * min(1.0, math.log1p(issue.comment_count or 0) / math.log1p(COMMENT_SATURATION)),
        "age": W_AGE * min(1.0, age_days / AGE_SATURATION_DAYS),
        "urgency": URGENCY.get(issue.urgency, URGENCY["medium"])["weight"],
        "scope": SCOPES.get(issue.affected_scope, SCOPES["street"])["weight"],
    }
    return {k: round(v, 1) for k, v in parts.items()}


def compute_priority(issue, now=None) -> int:
    return int(round(min(100.0, sum(priority_breakdown(issue, now).values()))))


def priority_level(score: int) -> dict:
    for threshold, key, label in PRIORITY_LEVELS:
        if (score or 0) >= threshold:
            return {"key": key, "label": label}
    return {"key": "low", "label": "Бага"}
