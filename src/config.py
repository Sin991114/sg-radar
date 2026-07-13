"""Central configuration: paths and scrape sources."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
DB_PATH = DATA_DIR / "tracker.db"
SITE_PATH = SITE_DIR / "index.html"
TZ = "Asia/Singapore"

# kind: "deal" -> authenticity scoring applies; "article" -> editorial guides;
# structured event sources (Eventbrite/Peatix) are kind="event" in their scrapers.
RSS_SOURCES = [
    dict(key="singpromos", name="SINGPromos", url="https://singpromos.com/feed/",
         kind="deal", default_category="shopping"),
    dict(key="moneydigest", name="MoneyDigest", url="https://www.moneydigest.sg/feed/",
         kind="deal", default_category="other"),
    dict(key="greatdeals", name="GreatDeals", url="https://www.greatdeals.com.sg/feed/",
         kind="deal", default_category="shopping"),
    dict(key="honeycombers", name="Honeycombers", url="https://thehoneycombers.com/singapore/feed/",
         kind="article", default_category="event"),
    dict(key="littledayout", name="Little Day Out", url="https://www.littledayout.com/feed/",
         kind="article", default_category="family"),
]

EVENTBRITE_URL = "https://www.eventbrite.sg/d/singapore--singapore/events/"
PEATIX_SEARCH = "https://peatix.com/search/events"

# --- Xiaohongshu via TikHub paid API (optional) -----------------------------
# TikHub runs the crawl server-side, so your own account/IP never touch XHS.
# Enable by putting your key in a `.tikhub_key` file at the project root
# (one line), or the TIKHUB_API_KEY env var. Get a key (free credit, no card)
# at https://user.tikhub.io  →  docs: https://docs.tikhub.io
TIKHUB_BASE = "https://api.tikhub.io/api/v1/xiaohongshu"
TIKHUB_SEARCH_PATH = "app_v2/search_notes"   # fallback if it 404s: "app/search_notes"
XHS_KEYWORDS = ["新加坡优惠", "新加坡折扣", "新加坡活动", "新加坡周末"]
XHS_PAGES_PER_KEYWORD = 1   # 1 page ≈ 20 notes/keyword; bump up once you top up credit


def load_tikhub_key() -> str:
    key = os.environ.get("TIKHUB_API_KEY", "").strip()
    if key:
        return key
    # accept the plain name and Notepad's auto ".txt"; utf-8-sig eats any BOM
    for name in (".tikhub_key", ".tikhub_key.txt"):
        f = ROOT / name
        if f.exists():
            k = f.read_text(encoding="utf-8-sig").strip()
            if k:
                return k
    return ""


# --- OpenRouter (optional LLM normalization) --------------------------------
# Free models rate-limit often, so the normalizer fetches the live free list
# and tries these preferences in order, falling back to rule-based on failure.
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL_PREFS = ["qwen3-next-80b", "qwen3-coder", "qwen", "glm",
                          "llama-3.3-70b", "gemma-4", "gemini-2.0-flash", "mistral", "gemma"]
NORMALIZE_BATCH = 12               # items per LLM request (batching beats the 50/day cap)
NORMALIZE_LLM_MAX_PER_RUN = 300    # covers a full backfill in one run; steady state is far less


def load_openrouter_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    for name in (".openrouter_key", ".openrouter_key.txt"):
        f = ROOT / name
        if f.exists():
            k = f.read_text(encoding="utf-8-sig").strip()
            if k:
                return k
    return ""
