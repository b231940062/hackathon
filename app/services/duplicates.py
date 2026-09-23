"""Давхардсан асуудал илрүүлэх энгийн алгоритм.

Гарчгийг жижиг үсэг болгож, туслах үгсийг хасаад, үг бүрийн эхний 3 үсгийг "үндэс" гэж үзнэ
(монгол хэлний нөхцөл залгаврыг ойролцоогоор арилгана: "замын" → "зам", "эвдэрсэн"/"эвдрэл" → "эвд").
Дараа нь Dice коэффициент + ангилал/хороо таарсан эсэхээр оноо гаргана.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Issue

STOPWORDS = {
    "нь", "ба", "бол", "энэ", "тэр", "эдгээр", "дээр", "доор", "их", "маш", "болон", "байна", "байгаа", "байсан",
    "асуудал", "асуудлыг", "асуудлын", "тухай", "бий", "юм", "гэж", "л", "ч", "та", "бид", "манай", "хүртэл",
    "дахь", "орчим", "орчмын", "хэт", "хэрэгтэй", "шаардлагатай", "мөн", "бас", "одоо", "ойр", "ойролцоо",
    "the", "and",
}
STOP_STEMS = {"хор", "дүү"}  # "хороо", "хорооны", "дүүрэг" зэрэг бараг бүх гарчигт давтагддаг үгс


def title_tokens(text: str) -> set[str]:
    text = (text or "").lower()
    text = re.sub(r"(\d+)\s*-?\s*(р|рт|рын|дугаар|дүгээр)\b", r"\1", text)
    words = re.findall(r"[a-zа-яөүё0-9]+", text)
    out = set()
    for w in words:
        if w in STOPWORDS:
            continue
        if w.isdigit():
            out.add(w)
            continue
        if len(w) < 2:
            continue
        stem = w[:3]
        if stem in STOP_STEMS:
            continue
        out.add(stem)
    return out


def dice(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def find_similar(db: Session, title: str, district_id: int | None = None, khoroo_id: int | None = None,
                 category: str | None = None, exclude_id: int | None = None, threshold: float = 0.55,
                 limit: int = 4) -> list[tuple[Issue, float]]:
    tokens = title_tokens(title)
    if not tokens:
        return []
    stmt = (select(Issue).where(Issue.status != "RESOLVED")
            .options(joinedload(Issue.district), joinedload(Issue.khoroo)))
    if district_id:
        stmt = stmt.where(Issue.district_id == district_id)
    if exclude_id:
        stmt = stmt.where(Issue.id != exclude_id)
    results = []
    for issue in db.scalars(stmt).unique():
        sim = dice(tokens, title_tokens(issue.title))
        if sim == 0:
            continue
        score = 0.6 * sim
        score += 0.25 if category and issue.category == category else 0
        if district_id:
            score += 0.15 if khoroo_id and issue.khoroo_id == khoroo_id else 0
        else:
            score = score / 0.85  # дүүрэг сонгоогүй үед зөвхөн гарчиг + ангиллаар
        if score >= threshold:
            results.append((issue, round(score, 2)))
    results.sort(key=lambda x: (-x[1], -x[0].support_count))
    return results[:limit]
