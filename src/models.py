"""Record model, text cleaning, category classification, promo fingerprint."""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass

from .dates import STRIP_DATES_RE

FOOD_WORDS = [
    "1-for-1", "1 for 1", "buffet", "dining", "dine", "restaurant", "cafe",
    "coffee", "bubble tea", "milk tea", "pizza", "burger", "sushi", "ramen",
    "fried chicken", "dessert", "ice cream", "bakery", "donut", "doughnut",
    "mala", "hotpot", "steamboat", "hawker", "kopitiam", "brunch", "menu",
    "meal", "makan", "snack", "beverage", "bento", "dim sum", "seafood",
    "mcdonald", "kfc", "starbucks", "subway", "jollibee", "domino",
    "pizza hut", "burger king", "mos burger", "ya kun", "toast box",
    "breadtalk", "dunkin", "swensen", "haidilao", "din tai fung", "genki",
    "sukiya", "yoshinoya", "liho", "gong cha", "chagee", "mixue", "luckin",
    "paris baguette", "old chang kee", "polar puffs", "bee cheng hiang",
    "美食", "探店", "餐厅", "咖啡", "甜品", "蛋糕", "火锅", "自助餐",
    "奶茶", "小吃", "下午茶", "早午餐", "日料", "烤肉", "好吃",
]
FAMILY_WORDS = [
    "kids", "kid-friendly", "children", "child", "family", "families",
    "parent", "baby", "toddler", "playground", "school holiday",
    "storytime", "story time", "junior", "little ones",
    "亲子", "遛娃", "儿童", "家庭", "小朋友", "室内乐园",
]
EVENT_WORDS = [
    "concert", "festival", "exhibition", "exhibit", "fair", "funfair",
    "carnival", "market", "bazaar", "pop-up", "popup", "roadshow",
    "workshop", "museum", "gallery", "performance", "gig", "parade",
    "fireworks", "national day", "ndp", "countdown", "open house",
    "screening", "meetup", "networking", "conference", "seminar",
    "marathon", "light show", "light-up", "lantern",
    "展览", "市集", "演唱会", "音乐节", "打卡", "灯光秀", "嘉年华",
    "演出", "展会", "快闪", "活动",
]
SHOP_WORDS = [
    "sale", "% off", "percent off", "discount", "clearance", "warehouse",
    "outlet", "promo code", "voucher", "cashback", "free gift", "bundle",
    "expo", "it show", "comex", "sitex", "fashion", "sneaker", "beauty",
    "skincare", "makeup", "electronics", "gadget", "furniture",
    "supermarket", "fairprice", "giant", "cold storage", "sheng siong",
    "don don donki", "uniqlo", "ikea", "shopee", "lazada", "qoo10",
    "watsons", "guardian", "sephora", "decathlon",
    "折扣", "优惠", "打折", "促销", "特价", "半价", "满减", "开业",
    "清仓", "大促", "羊毛", "返现", "优惠券", "代金券",
]

URL_CATEGORY_HINTS = [
    ("dining", "food"), ("restaurant", "food"), ("food", "food"),
    ("grocer", "food"), ("hawker", "food"),
    ("kids", "family"), ("baby", "family"), ("toys", "family"),
    ("family", "family"),
    ("events", "event"), ("exhibition", "event"), ("things-to-do", "event"),
    ("attraction", "event"),
    ("travel", "shopping"), ("fashion", "shopping"), ("apparel", "shopping"),
    ("electronics", "shopping"), ("gadget", "shopping"),
    ("beauty", "shopping"), ("home-living", "shopping"),
    ("department", "shopping"), ("supermarket", "shopping"),
]

TAG_RE = re.compile(r"<[^>]+>")
BOILERPLATE_RE = re.compile(r"\[?\s*Read more at.*?(\]|$)", re.I)


def clean_text(raw: str, limit: int = 280) -> str:
    s = html.unescape(TAG_RE.sub(" ", raw or ""))
    s = BOILERPLATE_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit].strip()


def classify(title: str, summary: str, url: str, default: str | None = None) -> str:
    path = (url or "").lower()
    for hint, cat in URL_CATEGORY_HINTS:
        if f"/{hint}" in path or f"-{hint}" in path or f"{hint}-" in path:
            return cat
    text = f" {title.lower()} {summary.lower()} "
    for words, cat in ((FAMILY_WORDS, "family"), (FOOD_WORDS, "food"),
                       (EVENT_WORDS, "event"), (SHOP_WORDS, "shopping")):
        if any(w in text for w in words):
            return cat
    return default or "other"


def fingerprint(title: str) -> str:
    """Date/number-insensitive signature so the same recurring promo
    posted on different days collapses to one key."""
    t = STRIP_DATES_RE.sub(" ", (title or "").lower())
    t = re.sub(r"\d+", " ", t)
    t = re.sub(r"[^a-z一-鿿]+", " ", t)
    words = sorted({w for w in t.split() if len(w) > 1})
    return " ".join(words)


@dataclass
class Record:
    source: str
    source_name: str
    kind: str            # deal | event | article
    category: str        # food | event | shopping | family | other
    title: str
    url: str
    summary: str = ""
    venue: str = ""
    date_start: str | None = None
    date_end: str | None = None
    published: str | None = None
    image: str | None = None
    rid: str | None = None    # stable identity override (e.g. XHS note id —
                              # note URLs carry rotating tokens, so URL != identity)
    extra: str | None = None  # JSON bag for source-specific fields (likes, keyword...)

    @property
    def id(self) -> str:
        key = self.rid or f"{self.source}|{self.url}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.title) if self.kind == "deal" else ""
