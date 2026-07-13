"""Normalize heterogeneous source text into one shape: merchant · offer · price.

Two layers:
  1. rule_normalize()  — free, instant, always runs. Good on the verbose
     English RSS deal titles ("BreadTalk Singapore 6 Buns for $10.80 …").
  2. llm_normalize()    — optional OpenRouter free models, batched, with a
     model-fallback chain. Handles the hard cases (Chinese/emoji Xiaohongshu
     clickbait) and judges real-deal vs marketing. Falls back to layer 1 on
     any failure, so the pipeline never blocks on the flaky free tier.

Result dict: {merchant, offer, price, auth, method}. `method` is "rule" or
the model id that produced it.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from . import config

# ---- layer 1: rule-based -----------------------------------------------------

CITY_RE = re.compile(r"(?i)\b(?:singapore|s['’]?pore|s'pore|sg)\b|新加坡|狮城|🇸🇬")
FILLER_RE = re.compile(r"(?i)\b(?:promotion|promo|is available|available now|available|latest)\b")
TAIL_RE = re.compile(r"(?i)\s*\b(?:until|till|from|valid|starting|happening)\b.*$")
PRICE_RES = [
    re.compile(r"\$\s?\d+(?:\.\d{1,2})?"),
    re.compile(r"(?i)\d{1,3}\s?%\s?(?:off|discount)"),
    re.compile(r"(?i)\bup\s?to\s?\d{1,3}\s?%"),
    re.compile(r"(?i)1[-\s]?for[-\s]?1"),
    re.compile(r"(?i)buy\s?\d\s?get\s?\d\s?free?"),
    re.compile(r"第二[杯份个]半价|买\d+送\d+|\d{1,3}\s?%\s?off|半价|折"),
]
STOP = {"the", "a", "an", "new", "get", "buy", "up", "s$", "free", "this"}


def _merchant(title: str) -> str:
    m = CITY_RE.split(title, 1)
    left = (m[0] if m else "").strip(" -–—|:·,")
    if left and left != title.strip() and 1 <= len(left) <= 28:
        return left
    # no city marker: take leading Capitalized brand-ish tokens
    toks = title.split()
    out = []
    for t in toks[:3]:
        if t.lower() in STOP or not t[:1].isalpha():
            break
        if t[:1].isupper() or not t.isascii():
            out.append(t)
        else:
            break
    cand = " ".join(out).strip(" -–—|:·,")
    return cand if 1 < len(cand) <= 28 else ""


def _price(text: str) -> str:
    for rx in PRICE_RES:
        m = rx.search(text)
        if m:
            return m.group(0).strip()
    return ""


def _offer(title: str, merchant: str) -> str:
    s = title
    if merchant:
        s = s.replace(merchant, "", 1)
    s = CITY_RE.sub(" ", s)
    s = FILLER_RE.sub(" ", s)
    s = TAIL_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip(" -–—|:·,.!！")
    return s[:52]


def rule_normalize(rec: dict) -> dict:
    title = rec.get("title", "") or ""
    summary = rec.get("summary", "") or ""
    merchant = _merchant(title) if rec.get("kind") != "xhs" else ""
    return {
        "merchant": merchant,
        "offer": _offer(title, merchant),
        "price": _price(f"{title} {summary}"),
        "auth": "",
        "method": "rule",
    }


# ---- layer 2: OpenRouter LLM (batched, model-fallback) -----------------------

SYS_PROMPT = (
    "把新加坡的优惠/活动/小红书帖子归一化成结构化 JSON。"
    '只返回一个对象 {"results":[...]}，results 每项对应一条输入、保持顺序，字段：'
    "i(输入序号,整数), merchant(商家/主体,没有则空字符串), "
    "offer(一句话说清是什么优惠/活动,≤16字,去掉城市名/emoji/废话,可用中文), "
    "price(价格或折扣,如 $10.80 / 80%off / 1-for-1 / 半价,没有则空), "
    "category(food/shopping/event/family/other 之一), "
    "auth(real_limited=真限时优惠 / evergreen_marketing=常态营销如天天up to X%off / "
    "promo_content=种草软文非具体优惠 / event=活动 / info=资讯攻略)。只输出 JSON，不要解释。"
)


def _free_models(key: str) -> list[str]:
    req = urllib.request.Request(f"{config.OPENROUTER_BASE}/models",
                                 headers={"Authorization": f"Bearer {key}"})
    data = json.load(urllib.request.urlopen(req, timeout=30))["data"]
    free = [m["id"] for m in data if m["id"].endswith(":free")]
    ordered, seen = [], set()
    for pref in config.OPENROUTER_MODEL_PREFS:
        for mid in free:
            if pref in mid and mid not in seen:
                ordered.append(mid)
                seen.add(mid)
    return ordered or free


def _clean(v) -> str:
    """LLM sometimes emits the string 'null'/'N/A' for empty fields."""
    s = str(v).strip() if v is not None else ""
    return "" if s.lower() in ("null", "none", "nil", "n/a", "na", "-", "") else s


def _call(key: str, model: str, items: list[dict]) -> dict:
    body = {
        "model": model, "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
        ],
    }
    req = urllib.request.Request(
        f"{config.OPENROUTER_BASE}/chat/completions",
        data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    resp = json.load(urllib.request.urlopen(req, timeout=90))
    return json.loads(resp["choices"][0]["message"]["content"])


def _llm_batch(key: str, models: list[str], items: list[dict]):
    """One batch through the model-fallback chain. Returns (mapped, used_model)
    or (None, None). Caller passes the last working model first so a run makes
    ~1 request/batch instead of re-walking the whole (mostly rate-limited) chain
    — important because failed requests still count toward the free daily cap."""
    payload = [{"i": it["i"], "title": it["title"], "summary": it["summary"][:200]}
               for it in items]
    for model in models:
        try:
            out = _call(key, model, payload)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503):      # rate-limited / upstream down → next model
                time.sleep(1.0)
                continue
            return None, None
        except Exception:
            time.sleep(1.0)
            continue
        results = out.get("results") if isinstance(out, dict) else out
        if not isinstance(results, list):
            continue
        mapped = {}
        for r in results:
            if isinstance(r, dict) and "i" in r:
                mapped[int(r["i"])] = {
                    "merchant": _clean(r.get("merchant")),
                    "offer": _clean(r.get("offer")),
                    "price": _clean(r.get("price")),
                    "auth": _clean(r.get("auth")),
                    "category": _clean(r.get("category")),
                    "method": model,
                }
        if mapped:
            return mapped, model
    return None, None


def normalize(records: list[dict], key: str | None) -> dict:
    """Return {record_id: norm}. Rule-based for all; LLM-enhance the messy
    kinds (deal/xhs) up to the per-run cap, gracefully falling back."""
    norms = {r["id"]: rule_normalize(r) for r in records}
    if not key:
        return norms

    messy = [r for r in records if r["kind"] in ("deal", "xhs")]
    messy.sort(key=lambda r: 0 if r["kind"] == "deal" else 1)  # deals (default view) first
    messy = messy[:config.NORMALIZE_LLM_MAX_PER_RUN]
    if not messy:
        return norms
    try:
        models = _free_models(key)
    except Exception as e:
        print(f"[normalize] 免费模型列表拉取失败，仅用规则清洗：{e}")
        return norms
    if not models:
        return norms

    idx = {i: r["id"] for i, r in enumerate(messy)}
    items = [{"i": i, "title": r.get("title", ""), "summary": r.get("summary", "")}
             for i, r in enumerate(messy)]
    done, active_model = 0, None
    for start in range(0, len(items), config.NORMALIZE_BATCH):
        batch = items[start:start + config.NORMALIZE_BATCH]
        order = ([active_model] + [m for m in models if m != active_model]
                 if active_model else models)
        mapped, used = _llm_batch(key, order, batch)
        if used:
            active_model = used     # stick with the model that just worked
        if not mapped:
            continue   # whole batch fell back to rule-based (already in norms)
        for i, fields in mapped.items():
            rid = idx.get(i)
            if not rid:
                continue
            base = norms[rid]
            # keep LLM fields where non-empty, else keep the rule baseline
            norms[rid] = {
                "merchant": fields["merchant"] or base["merchant"],
                "offer": fields["offer"] or base["offer"],
                "price": fields["price"] or base["price"],
                "auth": fields["auth"],
                "method": fields["method"],
            }
            done += 1
    print(f"[normalize] LLM 精修 {done}/{len(messy)} 条（其余用规则清洗）")
    return norms
