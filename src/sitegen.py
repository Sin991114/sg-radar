"""Render the aggregated records into a single self-contained dashboard.

Deal-forward, scannable, multi-source: every source (Xiaohongshu included,
as one source among many) folds into one filterable list. Filters: 品种
(category), 时间 (time window), 类型 (kind), plus sort and toggles.
"""
from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

LABEL_RANK = {"limited": 0, "watch": 1, "evergreen": 2}


# ---- display-level dedup (DB keeps every row; only the view merges) ---------

def _bigrams(s: str) -> set:
    s = re.sub(r"[\s\W_]+", "", (s or "").lower())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else ({s} if s else set())


def _containment(a: str, b: str) -> float:
    A, B = _bigrams(a), _bigrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


def assign_groups(records: list[dict]) -> dict:
    """Cluster deal/xhs rows that describe the same promo (same deal posted
    by several Xiaohongshu bloggers / several sites). Same merchant+price
    alone is NOT enough — McDonald's had two different $9.90 deals — so a
    text-similarity check always applies. Returns {record_id: group_id}."""
    def canon_price(p: str) -> str:
        p = (p or "").strip().lower().replace(" ", "")
        return "free" if p in ("free", "免费", "$0", "0") else p

    items = []
    for r in records:
        if r["kind"] not in ("deal", "xhs"):
            continue
        n = r.get("norm_obj") or {}
        m = (n.get("merchant") or "").strip().lower()
        o = n.get("offer") or r.get("title") or ""
        p = canon_price(n.get("price"))
        items.append((r["id"], m, o, p, f"{m}{o}"))

    parent = {i[0]: i[0] for i in items}

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for (ia, ma, oa, pa, fa), (ib, mb, ob, pb, fb) in itertools.combinations(items, 2):
        same = False
        if ma and ma == mb:
            oc = _containment(oa, ob)
            if pa and pa == pb and oc >= 0.3:
                same = True          # same merchant + same price + overlapping offer
            elif oc >= 0.55:
                same = True          # same merchant + near-same offer text
        elif _containment(fa, fb) >= 0.65:
            # different/absent merchant but same story — unless both declare
            # prices that disagree (e.g. SIA "From S$208" vs DBS "S$50 Off":
            # long shared brand text, genuinely different deals)
            if not (pa and pb and pa != pb):
                same = True
        if same:
            parent[find(ia)] = find(ib)

    return {i[0]: find(i[0]) for i in items}


def _ok(v) -> bool:
    """Drop null-ish LLM outputs so they don't render as the text 'null'."""
    return bool(v) and str(v).strip().lower() not in ("null", "none", "nil", "n/a", "-")


def _slim(r: dict, groups: dict | None = None) -> dict:
    published = r.get("published") or ""
    rec = published or r.get("date_start") or r.get("first_seen") or ""
    out = {
        "k": r["kind"], "c": r["category"], "t": r["title"], "u": r["url"],
        "v": r.get("venue") or "", "s": (r.get("summary") or "")[:150],
        "ds": r.get("date_start"), "de": r.get("date_end"),
        "sn": r["source_name"], "p": published[:10], "rec": rec[:10],
        "sd": r.get("seen_days", 0), "n": r.get("seen_count", 1),
    }
    if r.get("auth"):
        out["a"] = {"l": r["auth"]["label"], "r": r["auth"]["reasons"][:2]}
    if r.get("extra"):
        try:
            ex = json.loads(r["extra"])
            if ex.get("likes"):
                out["lk"] = ex["likes"]
            if ex.get("kw"):
                out["kw"] = ex["kw"]
        except json.JSONDecodeError:
            pass
    n = r.get("norm_obj")
    if n and r["kind"] in ("deal", "xhs"):   # uniform 商家·优惠·价格 display
        if _ok(n.get("merchant")):
            out["m"] = n["merchant"].strip()
        if _ok(n.get("offer")):
            out["o"] = n["offer"].strip()
        if _ok(n.get("price")):
            out["pr"] = n["price"].strip()
        if _ok(n.get("auth")):
            out["la"] = n["auth"].strip()   # LLM 真伪: real_limited/evergreen_marketing/promo_content/info/event
    if groups and r["id"] in groups:
        out["g"] = groups[r["id"]]
    return out


def render(records: list[dict], now, out_path) -> None:
    groups = assign_groups(records)
    data = [_slim(r, groups) for r in records]
    payload = json.dumps(data, ensure_ascii=False,
                         separators=(",", ":")).replace("<", "\\u003c")
    html = (TEMPLATE
            .replace("__JSON__", payload)
            .replace("__TODAY__", now.date().isoformat())
            .replace("__UPDATED__", now.strftime("%Y-%m-%d %H:%M")))
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


TEMPLATE = """<!doctype html>
<html lang="zh-Hans">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>狮城雷达 · SG Radar</title>
<link rel="icon" href='data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📡</text></svg>'>
<style>
:root{
  --paper:#f7f2e8; --paper2:#efe7d6; --card:#fffdf8; --ink:#241c12; --ink2:#786a55;
  --line:#e5dbc4; --red:#c8331f; --teal:#0d7d72; --amber:#a9740a; --green:#4d7c0f;
  --gray:#7c7264; --xhs:#e0463f; --chip:#efe7d3;
  --food:#d4432f; --shop:#b0730a; --event:#0d857a; --family:#5c8a2a; --other:#8a7a66;
}
@media (prefers-color-scheme:dark){:root{
  --paper:#16130d; --paper2:#1f1911; --card:#201a12; --ink:#efe7d5; --ink2:#a2947d;
  --line:#37301f; --red:#ff6d52; --teal:#37c2b2; --amber:#e0a637; --green:#a3d95c;
  --gray:#a89a86; --xhs:#ff6073; --chip:#2a2417;
  --food:#f0655d; --shop:#e0a637; --event:#37c2b2; --family:#9fd257; --other:#a99a82;
}}
:root[data-theme="light"]{
  --paper:#f7f2e8; --paper2:#efe7d6; --card:#fffdf8; --ink:#241c12; --ink2:#786a55;
  --line:#e5dbc4; --red:#c8331f; --teal:#0d7d72; --amber:#a9740a; --green:#4d7c0f;
  --gray:#7c7264; --xhs:#e0463f; --chip:#efe7d3;
  --food:#d4432f; --shop:#b0730a; --event:#0d857a; --family:#5c8a2a; --other:#8a7a66;
}
:root[data-theme="dark"]{
  --paper:#16130d; --paper2:#1f1911; --card:#201a12; --ink:#efe7d5; --ink2:#a2947d;
  --line:#37301f; --red:#ff6d52; --teal:#37c2b2; --amber:#e0a637; --green:#a3d95c;
  --gray:#a89a86; --xhs:#ff6073; --chip:#2a2417;
  --food:#f0655d; --shop:#e0a637; --event:#37c2b2; --family:#9fd257; --other:#a99a82;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{background:var(--paper);color:var(--ink);
  font:14.5px/1.5 "PingFang SC","Microsoft YaHei","Segoe UI",system-ui,sans-serif;
  background-image:radial-gradient(color-mix(in srgb,var(--ink) 6%,transparent) 1px,transparent 1px);
  background-size:23px 23px;}
.wrap{max-width:980px;margin:0 auto;padding:0 18px 80px}
a{color:inherit;text-decoration:none}

/* header + at-a-glance stats */
header{padding:30px 0 12px}
.top{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
h1{font-size:clamp(26px,5vw,38px);font-weight:800;letter-spacing:.5px;line-height:1}
h1 .red{color:var(--red)}
h1 .mono{font-size:.5em;color:var(--ink2);font-weight:700;letter-spacing:1px}
.sub{color:var(--ink2);font-size:13px;margin-top:8px}
.live{display:inline-flex;align-items:center;gap:6px;font-family:Consolas,monospace;font-size:11.5px;color:var(--ink2);margin-top:7px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--red);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
#theme{background:none;border:1px solid var(--line);border-radius:20px;padding:5px 11px;cursor:pointer;color:var(--ink2);font-size:15px;flex:none}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:18px}
@media(max-width:560px){.tiles{grid-template-columns:repeat(2,1fr)}}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;cursor:pointer;transition:.15s;text-align:left}
.tile:hover{border-color:var(--ink2);transform:translateY(-1px)}
.tile.on{border-color:var(--red);box-shadow:inset 0 0 0 1px var(--red)}
.tile b{font-family:"Bahnschrift",Consolas,sans-serif;font-size:27px;font-weight:800;display:block;line-height:1;font-variant-numeric:tabular-nums}
.tile.r b{color:var(--red)} .tile.g b{color:var(--green)} .tile.t b{color:var(--teal)} .tile.x b{color:var(--xhs)}
.tile span{font-size:11.5px;color:var(--ink2);display:block;margin-top:4px}

/* filter bar */
.controls{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--paper) 93%,transparent);
  backdrop-filter:blur(8px);padding:11px 0 9px;margin-bottom:2px;border-bottom:1px solid var(--line)}
#q{width:100%;padding:9px 14px;font-size:14px;color:var(--ink);background:var(--card);
  border:1.5px solid var(--line);border-radius:9px;outline:none}
#q:focus{border-color:var(--red)}
.frow{display:flex;gap:6px;margin-top:9px;flex-wrap:wrap;align-items:center}
.flabel{font-size:11px;color:var(--ink2);font-weight:700;letter-spacing:.5px;margin-right:2px}
.chip{border:1.4px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;
  padding:4px 11px;font-size:12.5px;cursor:pointer;transition:.14s;user-select:none;white-space:nowrap}
.chip:hover{border-color:var(--ink2)}
.chip.on{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.chip .cd{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:middle}
.chip.tog.on{background:var(--red);border-color:var(--red);color:#fff}
.count{font-size:12px;color:var(--ink2);margin-left:auto;font-variant-numeric:tabular-nums}

/* list */
ul{list-style:none;margin-top:8px}
.row{display:flex;gap:13px;padding:11px 8px 11px 12px;border-bottom:1px solid var(--line);
  border-left:3px solid transparent;animation:up .35s both;transition:background .12s}
.row:hover{background:var(--card)}
@keyframes up{from{opacity:0;transform:translateY(6px)}to{opacity:1}}
@media(prefers-reduced-motion:reduce){.row{animation:none}}
.row.cfood{border-left-color:var(--food)} .row.cshopping{border-left-color:var(--shop)}
.row.cevent{border-left-color:var(--event)} .row.cfamily{border-left-color:var(--family)}
.row.cother{border-left-color:var(--other)}
.when{flex:0 0 92px;font-family:"Bahnschrift",Consolas,sans-serif;line-height:1.25}
.when .d{display:block;font-size:14.5px;font-weight:700}
.when .d.urgent{color:var(--red)} .when .d.ok{color:var(--green)}
.when .wd{display:block;font-size:11px;color:var(--ink2)}
.when .ongoing{color:var(--teal);font-size:11px}
.when .likes{color:var(--xhs);font-weight:800;font-size:15px;font-variant-numeric:tabular-nums}
.body{min-width:0;flex:1}
.t{font-size:14.5px;font-weight:600;line-height:1.4}
.t:hover{color:var(--red)}
.t .mn{font-weight:800}
.t .pr{color:var(--red);font-weight:800;font-variant-numeric:tabular-nums;white-space:nowrap}
.meta{font-size:11.5px;color:var(--ink2);margin-top:3px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.ktag{font-size:10.5px;font-weight:800;border-radius:4px;padding:0 5px;letter-spacing:.3px}
.ktag.deal{background:var(--amber);color:#fff} .ktag.event{background:var(--teal);color:#fff}
.ktag.xhs{background:var(--xhs);color:#fff} .ktag.article{background:var(--gray);color:#fff}
.src{font-family:Consolas,monospace;font-size:10.5px;background:var(--chip);border-radius:4px;padding:0 5px}
.why{font-style:italic}
.badge{font-size:10.5px;font-weight:800;border-radius:4px;padding:1px 7px;letter-spacing:.3px;flex:none;align-self:center}
.badge.lim{background:var(--green);color:#fff} .badge.wat{border:1.4px solid var(--ink2);color:var(--ink2)}
.badge.eve{border:1.4px solid var(--red);color:var(--red)}
.atag{font-size:10.5px;font-weight:700;border-radius:4px;padding:0 6px}
.atag.am{color:var(--red);border:1px solid var(--red)}
.atag.pc{color:var(--amber);border:1px solid var(--amber)}
.atag.if{color:var(--ink2);border:1px solid var(--ink2)}
.dupchip{background:var(--chip);border-radius:999px;padding:0 7px;font-size:10.5px;color:var(--ink2);cursor:help}
.row.eve{opacity:.5} .row.eve .t{text-decoration:line-through} .row.eve:hover{opacity:.9}
.empty{padding:44px 12px;text-align:center;color:var(--ink2)}
footer{margin-top:44px;padding-top:14px;border-top:1px solid var(--line);font-size:12px;color:var(--ink2);line-height:1.85}
footer b{color:var(--ink)}
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="top">
    <div>
      <h1>狮城<span class="red">雷达</span> <span class="mono">SG RADAR</span></h1>
      <div class="sub">新加坡活动与优惠 · 8 来源每日聚合 · 自动识别「长期营销」假优惠</div>
      <div class="live"><span class="dot"></span>更新于 __UPDATED__ (SGT)</div>
    </div>
    <button id="theme" title="切换深浅色">🌗</button>
  </div>
  <div class="tiles">
    <div class="tile r" data-quick="limited"><b id="stLim">0</b><span>限时优惠</span></div>
    <div class="tile g" data-quick="urgent"><b id="stUrg">0</b><span>3 天内截止</span></div>
    <div class="tile t" data-quick="events7"><b id="stEv">0</b><span>未来 7 天活动</span></div>
    <div class="tile x" data-quick="xhs"><b id="stXhs">0</b><span>小红书情报</span></div>
  </div>
</header>

<div class="controls">
  <input id="q" type="search" placeholder="搜索：商家、活动、地点、关键词…">
  <div class="frow">
    <span class="flabel">品种</span>
    <button class="chip on" data-c="all">全部</button>
    <button class="chip" data-c="food"><span class="cd" style="background:var(--food)"></span>吃喝</button>
    <button class="chip" data-c="shopping"><span class="cd" style="background:var(--shop)"></span>购物</button>
    <button class="chip" data-c="event"><span class="cd" style="background:var(--event)"></span>活动</button>
    <button class="chip" data-c="family"><span class="cd" style="background:var(--family)"></span>亲子</button>
    <button class="chip" data-c="other"><span class="cd" style="background:var(--other)"></span>其他</button>
  </div>
  <div class="frow">
    <span class="flabel">时间</span>
    <button class="chip on" data-t="all">全部</button>
    <button class="chip" data-t="today">今天</button>
    <button class="chip" data-t="weekend">本周末</button>
    <button class="chip" data-t="7">7 天内</button>
    <button class="chip" data-t="30">30 天内</button>
  </div>
  <div class="frow">
    <span class="flabel">类型</span>
    <button class="chip" data-k="all">全部</button>
    <button class="chip on" data-k="deal">优惠</button>
    <button class="chip" data-k="event">活动</button>
    <button class="chip" data-k="xhs">小红书</button>
    <button class="chip" data-k="article">指南</button>
    <span class="flabel" style="margin-left:8px">排序</span>
    <button class="chip on" data-sort="new">最新</button>
    <button class="chip" data-sort="deadline">即将截止</button>
    <button class="chip" data-sort="hot">最热</button>
    <button class="chip tog" id="dated">只看带日期</button>
    <button class="chip tog" id="realOnly">只看真优惠</button>
    <button class="chip tog on" id="hideEver">隐藏长期营销 ✓</button>
    <span class="count" id="count"></span>
  </div>
</div>

<ul id="list"></ul>

<footer>
  <b>来源</b>：SINGPromos · MoneyDigest · GreatDeals · Honeycombers · Little Day Out · Eventbrite · Peatix · 小红书<br>
  <b>真实度</b>：<span class="badge lim">限时</span> 有明确截止 ·
  <span class="badge wat">待观察</span> 暂无截止 ·
  <span class="badge eve">长期营销</span> 同类促销反复出现（≥3 次、跨 ≥21 天），默认隐藏<br>
  双击 update.bat 抓取最新数据 · 历史存 data/tracker.db，识别越跑越准
</footer>

</div>
<script>
const DATA = __JSON__;
const TODAY = "__TODAY__";
const CATS = {food:"吃喝",shopping:"购物",event:"活动",family:"亲子",other:"其他"};
const KIND = {deal:["优惠","deal"],event:["活动","event"],xhs:["小红书","xhs"],article:["指南","article"]};
const AUTHTAG = {evergreen_marketing:["常态营销","am"],promo_content:["种草","pc"],info:["资讯","if"]};
const NOT_REAL = ["evergreen_marketing","promo_content","info"];  // LLM 判定为"非真优惠"
const WD = ["周日","周一","周二","周三","周四","周五","周六"];
const $ = s => document.querySelector(s);
const state = {c:"all", t:"all", k:"deal", sort:"new", q:"", dated:false, realOnly:false, hideEver:true};

function d2(iso){const[y,m,d]=iso.split("-").map(Number);return new Date(y,m-1,d);}
const today = d2(TODAY);
function addD(dt,n){const d=new Date(dt);d.setDate(d.getDate()+n);return d;}
function md(iso){const[,m,d]=iso.split("-").map(Number);return `${m}月${d}日`;}
function esc(s){return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function likeNum(s){s=String(s||"");if(s.includes("万"))return Math.round(parseFloat(s)*1e4)||0;return parseInt(s.replace(/[^0-9]/g,""))||0;}
function relDate(r){return r.k==="event"?(r.ds||r.rec):(r.de||r.rec);}

function timeWin(){
  if(state.t==="all") return null;
  if(state.t==="today") return [today,today];
  if(state.t==="weekend"){const w=today.getDay();return w===0?[today,today]:[addD(today,6-w),addD(today,7-w)];}
  return [today, addD(today,+state.t)];
}
function inWin(r,win){
  if(!win) return true;
  const[a,b]=win;
  if(r.k==="event"){if(!r.ds)return false;const s=d2(r.ds),e=r.de?d2(r.de):s;return s<=b&&e>=a;}
  const d=relDate(r); if(!d) return false;
  const x=d2(d); return x>=a&&x<=b;
}
function visible(r){
  if(state.k!=="all" && r.k!==state.k) return false;
  if(state.c!=="all" && r.c!==state.c) return false;
  if(state.hideEver && ((r.a&&r.a.l==="evergreen")||r.la==="evergreen_marketing")) return false;
  if(state.realOnly && NOT_REAL.includes(r.la)) return false;
  if(state.dated && !(r.ds||r.de)) return false;
  if(!inWin(r,timeWin())) return false;
  if(state.q){const h=(r.t+" "+r.v+" "+r.s+" "+r.sn+" "+(r.kw||"")).toLowerCase();
    for(const w of state.q.toLowerCase().split(/\\s+/)) if(w&&!h.includes(w)) return false;}
  return true;
}

function whenCol(r){
  if(r.k==="event"){
    if(!r.ds) return `<span class="wd">活动</span>`;
    const s=d2(r.ds),e=r.de?d2(r.de):s,on=s<=today&&e>=today;
    if(on&&r.de&&r.de!==r.ds) return `<span class="d">至${md(r.de)}</span><span class="ongoing">进行中</span>`;
    const rng=r.de&&r.de!==r.ds?`${md(r.ds)}–${md(r.de)}`:md(r.ds);
    return `<span class="d">${rng}</span><span class="wd">${r.de&&r.de!==r.ds?"":WD[s.getDay()]}</span>${on?'<span class="ongoing">进行中</span>':""}`;
  }
  if(r.k==="xhs"){
    const days=r.p?Math.round((today-d2(r.p))/864e5):null;
    const ago=days===null?"":days<=0?"今天":days===1?"昨天":days+"天前";
    return `<span class="likes">❤${likeNum(r.lk).toLocaleString()}</span><span class="wd">${ago}</span>`;
  }
  if(r.k==="deal"){
    const lbl=r.a?r.a.l:"watch";
    if(r.de){const e=d2(r.de),days=Math.round((e-today)/864e5);
      const cls=days<=3?"urgent":"ok";
      return `<span class="d ${cls}">${days<=0?"今天止":md(r.de)+"止"}</span><span class="wd">${lbl==="evergreen"?"长期":"限时"}</span>`;}
    return `<span class="wd">${r.p?md(r.p):"待观察"}</span>`;
  }
  return `<span class="wd">${r.p?md(r.p):"指南"}</span>`;
}

function titleHTML(r){
  if((r.k==="deal"||r.k==="xhs")&&r.o){    // normalized: 商家 · 一句话优惠 · 价格
    const m=r.m?`<span class="mn">${esc(r.m)}</span> `:"";
    const pr=r.pr?` <span class="pr">${esc(r.pr)}</span>`:"";
    return m+esc(r.o)+pr;
  }
  return esc(r.t);
}
function row(r,i){
  const[kcn,kcls]=KIND[r.k]||["",""];
  const bits=[`<span class="ktag ${kcls}">${kcn}</span>`,`<span class="src">${esc(r.sn)}</span>`,CATS[r.c]||r.c];
  if(r.v) bits.push("📍"+esc(r.v));
  if(r.k==="xhs"&&r.kw) bits.push("#"+esc(r.kw));
  if(r.k==="deal"){
    if(r.n>1) bits.push(`出现${r.n}次`);
    if(r.a&&r.a.r&&r.a.r[0]) bits.push(`<span class="why">${esc(r.a.r[0])}</span>`);
  }
  if((r.k==="xhs"||r.k==="article")&&(r.ds||r.de)) bits.push("📅提到"+md(r.de||r.ds));
  if(AUTHTAG[r.la]){const[tt,cc]=AUTHTAG[r.la];bits.push(`<span class="atag ${cc}">${tt}</span>`);}
  if(r.dups&&r.dups.length)
    bits.push(`<span class="dupchip" title="${esc(r.dups.map(d=>d.sn+"："+d.t).join("\\n"))}">+${r.dups.length} 同款</span>`);
  let badge="";
  if(r.k==="deal"){const l=r.a?r.a.l:"watch";
    badge=l==="limited"?'<span class="badge lim">限时</span>':l==="evergreen"?'<span class="badge eve">长期营销</span>':'<span class="badge wat">待观察</span>';}
  const eve=r.a&&r.a.l==="evergreen"?" eve":"";
  return `<li class="row c${r.c}${eve}" style="animation-delay:${Math.min(i*14,400)}ms">
    <div class="when">${whenCol(r)}</div>
    <div class="body"><a class="t" href="${esc(r.u)}" target="_blank" rel="noopener" title="${esc(r.t)}">${titleHTML(r)}</a>
      <div class="meta">${bits.join(" · ")}</div></div>
    ${badge}</li>`;
}

function render(){
  let rows=DATA.filter(visible);
  const big="9999-99-99";
  if(state.sort==="new") rows.sort((a,b)=>(b.rec||"").localeCompare(a.rec||""));
  else if(state.sort==="deadline") rows.sort((a,b)=>(a.de||big).localeCompare(b.de||big));
  else rows.sort((a,b)=>likeNum(b.lk)-likeNum(a.lk));
  // display-level dedup: keep the first row of each group in current sort,
  // fold the rest into a "+N 同款" chip on the representative
  const byG=new Map(), kept=[];
  for(const r of rows){
    if(r.g && byG.has(r.g)){ byG.get(r.g).dups.push(r); continue; }
    r.dups=[]; if(r.g) byG.set(r.g,r);
    kept.push(r);
  }
  rows=kept;
  $("#list").innerHTML = rows.length?rows.map(row).join(""):`<li class="empty">没有匹配的条目 — 换个筛选试试</li>`;
  $("#count").textContent = rows.length+" 条";
}

// stats
const win7=[today,addD(today,7)];
function evIn(r,win){if(r.k!=="event"||!r.ds)return false;const s=d2(r.ds),e=r.de?d2(r.de):s;return s<=win[1]&&e>=win[0];}
$("#stLim").textContent = DATA.filter(r=>r.a&&r.a.l==="limited").length;
$("#stUrg").textContent = DATA.filter(r=>r.k==="deal"&&r.de&&Math.round((d2(r.de)-today)/864e5)>=0&&Math.round((d2(r.de)-today)/864e5)<=3&&!(r.a&&r.a.l==="evergreen")).length;
$("#stEv").textContent  = DATA.filter(r=>evIn(r,win7)).length;
$("#stXhs").textContent = DATA.filter(r=>r.k==="xhs").length;

// quick tiles → preset filters
const QUICK={
  limited:()=>{setKind("deal");state.dated=false;syncDated();},
  urgent:()=>{setKind("deal");state.sort="deadline";syncSort();state.t="7";syncT();},
  events7:()=>{setKind("event");state.t="7";syncT();},
  xhs:()=>{setKind("xhs");},
};
function setKind(k){state.k=k;document.querySelectorAll(".chip[data-k]").forEach(x=>x.classList.toggle("on",x.dataset.k===k));}
function syncT(){document.querySelectorAll(".chip[data-t]").forEach(x=>x.classList.toggle("on",x.dataset.t===state.t));}
function syncSort(){document.querySelectorAll(".chip[data-sort]").forEach(x=>x.classList.toggle("on",x.dataset.sort===state.sort));}
function syncDated(){$("#dated").classList.toggle("on",state.dated);$("#dated").textContent=state.dated?"只看带日期 ✓":"只看带日期";}
document.querySelectorAll(".tile").forEach(t=>t.onclick=()=>{
  document.querySelectorAll(".tile").forEach(x=>x.classList.remove("on"));t.classList.add("on");
  (QUICK[t.dataset.quick]||(()=>{}))();render();
});

function bind(sel,attr,key){document.querySelectorAll(sel).forEach(b=>b.onclick=()=>{
  document.querySelectorAll(sel).forEach(x=>x.classList.remove("on"));b.classList.add("on");
  state[key]=b.dataset[attr];render();});}
bind(".chip[data-c]","c","c"); bind(".chip[data-t]","t","t");
bind(".chip[data-k]","k","k"); bind(".chip[data-sort]","sort","sort");
$("#dated").onclick=()=>{state.dated=!state.dated;syncDated();render();};
$("#realOnly").onclick=e=>{state.realOnly=!state.realOnly;e.currentTarget.classList.toggle("on",state.realOnly);
  e.currentTarget.textContent=state.realOnly?"只看真优惠 ✓":"只看真优惠";render();};
$("#hideEver").onclick=e=>{state.hideEver=!state.hideEver;e.currentTarget.classList.toggle("on",state.hideEver);
  e.currentTarget.textContent=state.hideEver?"隐藏长期营销 ✓":"显示长期营销";render();};
let qt;$("#q").oninput=e=>{clearTimeout(qt);qt=setTimeout(()=>{state.q=e.target.value.trim();render();},150);};
$("#theme").onclick=()=>{const r=document.documentElement;
  const dark=r.dataset.theme==="dark"||(!r.dataset.theme&&matchMedia("(prefers-color-scheme:dark)").matches);
  r.dataset.theme=dark?"light":"dark";};
render();
</script>
</body>
</html>
"""
