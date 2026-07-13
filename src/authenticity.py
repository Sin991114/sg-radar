"""Score how real a deal is: deadline, specificity, and recurrence signals.

Labels: "limited" (has a real deadline), "watch" (unproven),
"evergreen" (same promo keeps reappearing -> marketing, not a deal).
"""
from __future__ import annotations

import re
from datetime import date

CAMPAIGN_RE = re.compile(
    r"(great singapore sale|\bgss\b|7\.7|8\.8|9\.9|10\.10|11\.11|12\.12|"
    r"black friday|cyber monday|national day|\bndp\b|payday)", re.I)
VAGUE_RE = re.compile(r"(?:up\s*to|as\s+low\s+as|低至)\s*\d{1,3}\s*%", re.I)
PRICE_RE = re.compile(r"\$\s*\d+(?:\.\d{1,2})?")

EVERGREEN_MIN_HITS = 3
EVERGREEN_MIN_SPAN_DAYS = 21


def assess(rec: dict, today: date, recurrence) -> dict:
    """rec is a DB row dict; recurrence is (hits, span_days) or None."""
    reasons, score = [], 0
    text = f"{rec.get('title', '')} {rec.get('summary', '')}"

    if rec.get("date_end"):
        score += 2
        reasons.append(f"有明确截止日期 {rec['date_end']}")
    else:
        score -= 1
        reasons.append("未写截止日期")

    if VAGUE_RE.search(text):
        score -= 2
        reasons.append("“up to / 低至”式话术，未见具体商品")
    if PRICE_RE.search(text):
        score += 1
        reasons.append("有具体价格")
    if CAMPAIGN_RE.search(text):
        score += 1
        reasons.append("绑定大促节点")

    label = "limited" if rec.get("date_end") else "watch"
    if recurrence:
        hits, span = recurrence
        if hits >= EVERGREEN_MIN_HITS and span >= EVERGREEN_MIN_SPAN_DAYS:
            label = "evergreen"
            reasons.insert(0, f"近 {span} 天内同类促销出现 {hits} 次，属常态营销")
        elif hits >= 2:
            reasons.append(f"{span} 天内已重复出现 {hits} 次，持续观察")

    return {"label": label, "score": score, "reasons": reasons}
