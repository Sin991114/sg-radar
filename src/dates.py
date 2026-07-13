"""Extract Singapore-style promotion/event dates from free text.

Feeds write dates like "Until 14 July 2026", "10 - 20 Jul", "from 1 to
15 August", "July 14, 2026". Year is often omitted; we resolve it
relative to today with a rollover window.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from dateutil import parser as dateparser

MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
WEEKDAY = r"\b(?:mon|tues?|wed(?:nes)?|thur?s?|fri|sat(?:ur)?|sun)(?:day)?s?\b"
_DMY = rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH}(?:\s+\d{{4}})?"
_MDY = rf"{MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?"
_ANY = rf"(?:{_DMY}|{_MDY})"

RANGE_RE = re.compile(rf"\b({_ANY})\s*(?:-|–|—|~|to|till|until)\s*({_ANY})", re.I)
MSPAN_RE = re.compile(
    rf"\b({MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|—|to|till|until|&|and)\s*(\d{{1,2}})(?:st|nd|rd|th)?\b",
    re.I)
DAYSPAN_RE = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|—|&|and|to)\s*({_DMY})", re.I)
UNTIL_RE = re.compile(
    rf"\b(?:until|till|til|u\.p\.|ends?\s+on|ends|through|before|by|valid\s+thru)\s+({_ANY})", re.I)
ON_RE = re.compile(rf"\b(?:on|happening|this)\s+({_ANY})", re.I)
CN_DATE = r"\d{1,2}\s*月\s*\d{1,2}\s*日?"
CN_RANGE_RE = re.compile(rf"({CN_DATE})\s*[-–—~至到]\s*({CN_DATE})")
CN_DAYSPAN_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日?\s*[-–—~至到]\s*(\d{1,2})\s*日")
CN_UNTIL_RE = re.compile(rf"(?:截止|截至|有效期?至|限时至|到)\s*({CN_DATE})")
CN_SINGLE_RE = re.compile(rf"({CN_DATE})")
STRIP_DATES_RE = re.compile(rf"{_ANY}|{CN_DATE}|\b\d{{4}}\b|{MONTH}|{WEEKDAY}", re.I)


def _parse(raw: str, today: date):
    """Parse a date fragment; returns (date, had_explicit_year) or None."""
    has_year = bool(re.search(r"\d{4}", raw))
    try:
        d = dateparser.parse(
            raw, dayfirst=True,
            default=datetime(today.year, today.month, today.day)).date()
    except (ValueError, OverflowError, TypeError):
        return None
    return d, has_year


def _roll(parsed, today: date):
    """Fix omitted years and reject absurd results."""
    if parsed is None:
        return None
    d, has_year = parsed
    if not has_year and d < today - timedelta(days=45):
        try:
            d = d.replace(year=d.year + 1)
        except ValueError:
            return None
    if d > today + timedelta(days=550) or d < today - timedelta(days=400):
        return None
    return d


def _parse_cn(frag: str, today: date):
    """'7月19日' -> date, with the same no-year rollover as _roll."""
    m = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})", frag)
    if not m:
        return None
    return _mk_cn(today.year, int(m.group(1)), int(m.group(2)), today)


def _mk_cn(year: int, month: int, day: int, today: date):
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    return _roll((d, False), today)


def extract_dates(text: str, today: date):
    """Return (start_iso, end_iso); either may be None."""
    t = " ".join((text or "").split())

    m = RANGE_RE.search(t)
    if m:
        s = _roll(_parse(m.group(1), today), today)
        e = _roll(_parse(m.group(2), today), today)
        if s and e:
            if e < s:
                try:
                    e = e.replace(year=e.year + 1)
                except ValueError:
                    e = None
            if e and 0 <= (e - s).days <= 200:
                return s.isoformat(), e.isoformat()

    m = MSPAN_RE.search(t)
    if m:
        s = _roll(_parse(f"{m.group(2)} {m.group(1)}", today), today)
        e = _roll(_parse(f"{m.group(3)} {m.group(1)}", today), today)
        if s and e and s <= e:
            return s.isoformat(), e.isoformat()

    m = DAYSPAN_RE.search(t)
    if m:
        e = _roll(_parse(m.group(2), today), today)
        if e:
            try:
                s = e.replace(day=int(m.group(1)))
            except ValueError:
                s = None
            if s and s <= e:
                return s.isoformat(), e.isoformat()

    m = UNTIL_RE.search(t)
    if m:
        # past deadlines are valid data — they mean "expired", and the
        # active-selection query is what filters those out
        e = _roll(_parse(m.group(1), today), today)
        if e:
            return None, e.isoformat()

    m = ON_RE.search(t)
    if m:
        s = _roll(_parse(m.group(1), today), today)
        if s:
            return s.isoformat(), None

    m = CN_RANGE_RE.search(t)
    if m:
        s, e = _parse_cn(m.group(1), today), _parse_cn(m.group(2), today)
        if s and e:
            if e < s:
                e = _mk_cn(e.year + 1, e.month, e.day, today)
            if e and 0 <= (e - s).days <= 200:
                return s.isoformat(), e.isoformat()

    m = CN_DAYSPAN_RE.search(t)  # 7月19-20日 / 7月19日-20日
    if m:
        mo = int(m.group(1))
        s = _mk_cn(today.year, mo, int(m.group(2)), today)
        e = _mk_cn(today.year, mo, int(m.group(3)), today)
        if s and e and s <= e:
            return s.isoformat(), e.isoformat()

    m = CN_UNTIL_RE.search(t)  # 截止7月15日 / 到7月15日
    if m:
        e = _parse_cn(m.group(1), today)
        if e:
            return None, e.isoformat()

    m = CN_SINGLE_RE.search(t)
    if m:
        s = _parse_cn(m.group(1), today)
        if s:
            return s.isoformat(), None

    return None, None
