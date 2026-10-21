"""
把各個 repo 產出的資料整合成一個靜態網站（輸出到 site/）。

資料來源（由 workflow checkout 到 SOURCES_DIR 底下）：
  tim-lu/data/digests/{date}.json             每日總經摘要（macro_digest.py 產出）
  investment-team/data/reports/{date}.json    每週基本面報告的結構化資料（fundamentals.py 產出）
  investment-team/data/reports/{date}.md      同一份報告的完整文字版，放在「完整報告」頁

網站本身不打任何外部 API，只讀這些檔案；所以重建很便宜，壞了也不會影響原本寄信的流程。

版面原則：每頁先給數字與結論，長文字一律收進「展開」區塊。
"""

import html
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import markdown

import icons
from ui_icons import ui
import portfolio
import visuals
from visuals import funnel, monogram, revenue_bars, score_bar, short_name, stock_logo

ROOT = Path(__file__).parent
SOURCES_DIR = Path(os.environ.get("SOURCES_DIR", ROOT / "sources"))
OUT_DIR = Path(os.environ.get("OUT_DIR", ROOT / "site"))
TAIPEI = timezone(timedelta(hours=8))

DIGEST_DIR = SOURCES_DIR / "tim-lu" / "data" / "digests"
REPORT_DIR = SOURCES_DIR / "investment-team" / "data" / "reports"
SCREEN_DIR = SOURCES_DIR / "investment-team" / "data" / "screens"   # 每個交易日收盤後更新的研究候選（daily_screen.py）
STATEMENT_DIR = SOURCES_DIR / "trade-report" / "data" / "statements"
PICKS_DIR = ROOT / "data" / "picks"

# (路徑, 標籤, 手機上的短標籤)
NAV = [("index.html", "總覽", "總覽"), ("pick/index.html", "每日一檔", "一檔"), ("market/index.html", "台股", "台股"), ("us/index.html", "美股", "美股"), ("fx/index.html", "匯率", "匯率"), ("news/index.html", "即時快報", "快報"),
       ("daily/index.html", "每日總經", "總經"), ("weekly/index.html", "每週研究", "研究"), ("supply/index.html", "供應鏈", "供應鏈"),
       ("whales/index.html", "大佬持股", "大佬"),
       ("sim/index.html", "模擬交易", "模擬"), ("robot/index.html", "專屬投資顧問", "顧問"),
       ("portfolio/index.html", "投資", "投資")]
# 太泛的關鍵字不當作新聞標籤
GENERIC_KW = {"TOP", "headline", "台股", "美股", "國際股", "科技", "產業", "鉅亨速報", "大盤", "股市", "市場", "經濟", "投資", "個股"}
WEEKDAYS = "一二三四五六日"
STYLE_LABEL = {"value": ("價值型", "持有 5–10 年"), "growth": ("成長型", "持有約 1 年")}
DISCLAIMER = "研究素材整理，不是買賣建議，也不預測股價。"


def e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def zh_date(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.year} 年 {d.month} 月 {d.day} 日・星期{WEEKDAYS[d.weekday()]}"


def pct(x, digits=1, ratio=True) -> str:
    """ratio=True 表示 0.123 → 12.3%；False 表示已經是百分比數字。"""
    if x is None:
        return "—"
    return f"{x * 100 if ratio else x:.{digits}f}%"


def num(x, digits=1) -> str:
    return "—" if x is None else f"{x:,.{digits}f}"


def signed_cls(x) -> str:
    # 台灣習慣：紅漲綠跌
    return "" if not x else ("pos" if x > 0 else "neg")


# ---------- 版面 ----------

def page(title: str, body: str, depth: int, active: str) -> str:
    prefix = "../" * depth
    nav = "".join(
        f'<a href="{prefix}{href}"{" class=\"on\"" if href == active else ""}><span class="l">{label}</span><span class="s">{short}</span></a>'
        for href, label, short in NAV
    )
    built = visuals.floor5(datetime.now(TAIPEI).isoformat(), "%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{e(title)} · Craig 財經站</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="top"><div class="wrap">
  <a class="brand" href="{prefix}index.html"><span class="mark">C</span><span class="brand-text">Craig 財經站</span></a>
  <nav>{nav}</nav>
</div></header>
<div class="tickerbar" aria-label="即時行情"><span class="tk-live"><span class="live-dot"></span><span class="live-stamp">即時行情</span></span><div class="tk-view" id="tk"></div></div>
{body}
<footer><div class="wrap">更新於 {built}（台北時間）・{DISCLAIMER}</div></footer>
<script src="{prefix}glossary.js" defer></script>
<script src="{prefix}site.js" defer></script>
</body>
</html>
"""


def hero(kicker: str, title: str, sub: str = "", extra: str = "") -> str:
    sub_html = f'<p class="hero-sub">{sub}</p>' if sub else ""
    return (f'<section class="hero"><div class="wrap"><div class="kicker">{kicker}</div>'
            f'<h1>{title}</h1>{sub_html}{extra}</div></section>')


def section(title: str, body: str, note: str = "", link: str = "") -> str:
    note_html = f'<span class="sec-note">{note}</span>' if note else ""
    link_html = f'<a class="sec-link" href="{link[0]}">{link[1]} →</a>' if link else ""
    return (f'<section class="sec"><div class="sec-head"><h2>{title}</h2>{note_html}{link_html}</div>{body}</section>')


def pager(prev_href, prev_label, next_href, next_label, index_href) -> str:
    left = f'<a href="{prev_href}">← {e(prev_label)}</a>' if prev_href else "<span></span>"
    right = f'<a href="{next_href}">{e(next_label)} →</a>' if next_href else "<span></span>"
    return f'<nav class="pager">{left}<a href="{index_href}">全部日期</a>{right}</nav>'


# ---------- 每日總經 ----------

def load_digests() -> list[dict]:
    if not DIGEST_DIR.is_dir():
        print(f"⚠️ 找不到 {DIGEST_DIR}，每日總經區塊會是空的", file=sys.stderr)
        return []
    digests = []
    for f in sorted(DIGEST_DIR.glob("*.json"), reverse=True):
        try:
            digests.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"⚠️ 略過無法解析的 {f.name}：{exc}", file=sys.stderr)
    return digests


def parse_structured_summary(text: str) -> list[dict]:
    """同 macro_digest.parse_structured_summary：把『【標題】\\n- 條列』切成區塊。"""
    sections: list[dict] = []
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if m := re.match(r"^【(.+?)】$", line):
            current = {"header": m.group(1), "items": []}
            sections.append(current)
            continue
        item = line[2:].strip() if line.startswith(("- ", "・")) else line
        if current is None:
            current = {"header": "", "items": []}
            sections.append(current)
        current["items"].append(item)
    return sections


CITE_WORDS = ("段永平", "巴菲特", "芒格", "李錄", "FinMind", "SEC", "背景知識")


def strip_cites(text: str) -> str:
    """拿掉「【段永平】」「（段永平、李錄）」「【FinMind FY2025】」這類出處標記，用在摘要預覽。"""
    text = re.sub(r"【[^】]*】", "", text)
    text = re.sub(r"[（(]([^（）()]*)[）)]", lambda m: "" if any(w in m.group(1) for w in CITE_WORDS) else m.group(0), text)
    text = re.sub(r"[、，；\s]+([。；，]|$)", r"\1", text.replace("**", ""))
    return text.strip()


def clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n].rstrip("，、；。 ") + "…"


def fred_tiles(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">尚無總經數據</p>'
    tiles = []
    for r in rows:
        m = re.match(r"^(.*?)\s*\((.+)\)$", r.get("label", ""))
        label, unit = (m.group(1), m.group(2)) if m else (r.get("label", ""), "")
        try:
            latest = float(r["latest_value"])
            value = f"{latest:,.2f}" if latest < 1000 else f"{latest:,.0f}"
        except (TypeError, ValueError, KeyError):
            latest, value = None, e(r.get("latest_value") or "—")
        try:
            diff = latest - float(r["previous_value"])
            arrow = "▲" if diff > 0 else "▼" if diff < 0 else "–"
            change = f'<span class="chg {signed_cls(diff)}">{arrow} {abs(diff):,.2f}</span>'
        except (TypeError, ValueError, KeyError):
            change = ""
        # 「%」放在數字旁邊；較長的單位（十億美元）放在標題，避免擠到換行
        label_html = e(label) + (f"<small>・{e(unit)}</small>" if unit and unit != "%" else "")
        unit_html = '<span class="unit">%</span>' if unit == "%" else ""
        tiles.append(
            f'<div class="stat"><div class="stat-label">{label_html}</div>'
            f'<div class="stat-value" data-count>{value}{unit_html}</div>'
            f'<div class="stat-foot">{change}<span>{e(r.get("latest_date") or "")}</span></div></div>'
        )
    return '<div class="stats">' + "".join(tiles) + "</div>"


# 工商時報那一區是朋友的 AI 摘要；對方額度用完或文章太長時，信裡會直接放錯誤訊息
SUMMARY_FAILED = re.compile(r"摘要失敗|Error code: \d{3}|Rate limit|Request too large|未知錯誤")


def summary_failed(a: dict) -> bool:
    return bool(a.get("summary_failed") or SUMMARY_FAILED.search(a.get("structured_summary") or ""))


def article_lede(a: dict) -> str:
    if not a.get("structured_summary") or summary_failed(a):
        return ""
    for sec in parse_structured_summary(a["structured_summary"]):
        if sec["items"]:
            return sec["items"][0]
    return ""


def article_time(a: dict) -> str:
    return datetime.fromtimestamp(a["publishAt"], tz=TAIPEI).strftime("%m/%d %H:%M") if a.get("publishAt") else ""


def keywords(a: dict, n: int = 3) -> str:
    kws = [k for k in a.get("keywords") or [] if k not in GENERIC_KW and len(k) <= 8][:n]
    return "".join(f"<span>#{e(k)}</span>" for k in kws)


def render_article(a: dict, section_name: str, featured: bool = False) -> str:
    meta = " ・ ".join(x for x in [e(a.get("author")), article_time(a)] if x)
    lede = article_lede(a)
    full = ""
    if summary_failed(a):
        full = '<p class="news-nosum">這篇的 AI 摘要沒有產生（來源端的 AI 額度用完或文章太長），請點「原文」閱讀。</p>'
    elif a.get("structured_summary"):
        parts = ""
        for sec in parse_structured_summary(a["structured_summary"]):
            head = f"<h4>{e(sec['header'])}</h4>" if sec["header"] else ""
            parts += head + "<ul>" + "".join(f"<li>{e(it)}</li>" for it in sec["items"]) + "</ul>"
        full = f'<details class="more"><summary>完整摘要</summary><div class="more-body">{parts}</div></details>'
    link = f'<a class="ext" href="{e(a["url"])}" target="_blank" rel="noopener">原文 ↗</a>' if a.get("url") else ""
    kws = keywords(a)
    return (f'<article class="news{" featured" if featured else ""}">{icons.article_icon(a)}<div class="news-in">'
            f'<div class="news-meta"><span>{meta}</span>{link}</div>'
            f'<h3>{e(a.get("title"))}</h3>'
            + (f'<p class="lede">{e(lede)}</p>' if lede else "")
            + (f'<div class="kws">{kws}</div>' if kws else "")
            + full + "</div></article>")


def digest_highlights(d: dict) -> str:
    """主視覺裡的「今日三大重點」：每個分類第一則新聞的第一句重點。"""
    items = []
    for sec in d.get("news_sections", []):
        for a in sec.get("articles", [])[:1]:
            lede = article_lede(a)
            if lede:
                items.append((sec.get("name"), clip(lede, 60)))
    if not items:
        return ""
    lis = "".join(f'<li><span class="hl-n">{i}</span><span class="hl-t"><small>{e(n)}</small>{e(t)}</span></li>'
                  for i, (n, t) in enumerate(items[:3], 1))
    return f'<ol class="digest-hero">{lis}</ol>'


def render_digest_page(d: dict, prev_d, next_d) -> str:
    total = sum(len(s.get("articles", [])) for s in d.get("news_sections", []))
    body = hero("每日總經", zh_date(d["date"]), f"{total} 則新聞・{len(d.get('fred', []))} 項美國總經數據", digest_highlights(d))
    body += '<main class="wrap">'
    body += section("美國總經數據", fred_tiles(d.get("fred", [])), "FRED")
    for sec in d.get("news_sections", []):
        arts = sorted(sec.get("articles", []), key=summary_failed)  # 有摘要的排前面，摘要失敗的放最後
        if arts:
            cards = "".join(render_article(a, sec.get("name") or "", featured=(i == 0)) for i, a in enumerate(arts))
            body += section(e(sec.get("name")), f'<div class="news-list">{cards}</div>', f"{e(sec.get('source'))}・{len(arts)} 則")
    body += pager(prev_d and f"{prev_d['date']}.html", prev_d and prev_d["date"],
                  next_d and f"{next_d['date']}.html", next_d and next_d["date"], "index.html")
    return body + "</main>"


def headline_list(d: dict, limit: int, depth_prefix: str) -> str:
    items = []
    for sec in d.get("news_sections", []):
        for a in sec.get("articles", []):
            items.append((sec.get("name"), a))
    if not items:
        return '<p class="empty">今日沒有新聞</p>'
    lis = "".join(
        f'<li><span class="pill">{e(name)}</span><a href="{depth_prefix}daily/{d["date"]}.html">{e(a.get("title"))}</a>'
        f'<span class="time">{article_time(a)}</span></li>'
        for name, a in items[:limit]
    )
    return f'<ol class="headlines">{lis}</ol>'


# ---------- 每週研究 ----------

# 完整報告裡的股名也去掉「*」：只拿掉緊接在中文字後、後面不是另一個「*」的那個（不動 Markdown 粗體 **）
STAR_AFTER_NAME = re.compile(r"(?<=[\u4e00-\u9fff])\*(?!\*)")


def strip_stars(obj):
    """報告 JSON 裡 AI 分析文字也會寫「愛普*」，所有字串一併處理。"""
    if isinstance(obj, str):
        return STAR_AFTER_NAME.sub("", obj)
    if isinstance(obj, dict):
        return {k: strip_stars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_stars(x) for x in obj]
    return obj


def load_reports() -> list[dict]:
    if not REPORT_DIR.is_dir():
        print(f"⚠️ 找不到 {REPORT_DIR}，每週研究區塊會是空的", file=sys.stderr)
        return []
    reports = []
    for f in sorted(REPORT_DIR.glob("*.json"), reverse=True):
        try:
            data = strip_stars(visuals.clean_names(json.loads(f.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"⚠️ 略過無法解析的 {f.name}：{exc}", file=sys.stderr)
            continue
        # 早期版本的 JSON 只是公司清單，沒有台股篩選
        screen, companies = (data.get("screen"), data.get("companies", [])) if isinstance(data, dict) else (None, data)
        md = f.with_suffix(".md")
        reports.append({"date": f.stem, "screen": screen, "companies": companies,
                        "md": STAR_AFTER_NAME.sub("", md.read_text(encoding="utf-8")) if md.exists() else None})
    return reports


def screen_ok(s) -> bool:
    """新版篩選且有實際跑出結果；全市場資料抓不齊的那幾次（初篩 0 家或有 error）不算。"""
    return bool(s) and "value" in s and not s.get("error") and sum((s.get("prefilter") or {}).values()) > 0


def load_latest_screen(reports: list[dict]) -> dict | None:
    """目前最新的研究候選：每日篩選比週報新就用每日的，否則用最近一份資料完整的週報。"""
    daily = None
    f = SCREEN_DIR / "latest.json"
    if f.exists():
        try:
            daily = visuals.clean_names(json.loads(f.read_text(encoding="utf-8")))
            daily["date"] = daily.get("generated_at", "")[:10]
            daily["source"] = "daily"
        except (json.JSONDecodeError, OSError) as exc:
            print(f"⚠️ 每日篩選讀取失敗：{exc}", file=sys.stderr)
            daily = None
    weekly = next(({**r["screen"], "date": r["date"], "source": "weekly"} for r in reports if screen_ok(r["screen"])), None)
    cands = [x for x in (daily, weekly) if x and screen_ok(x)]
    return max(cands, key=lambda x: (x["date"], x["source"] == "daily")) if cands else None


def bucket(cands: list[dict]) -> dict:
    return {
        "full": [c for c in cands if c["n_fail"] == 0 and not c["flags"]],
        "near": [c for c in cands if c["n_fail"] == 1 and not c["flags"]],
        "flagged": [c for c in cands if c["flags"]],
    }


def rev_dots(c: dict) -> str:
    """近 5 期月營收年增：紅點正成長、綠點負成長。"""
    series = (c.get("detail") or {}).get("rev_yoy") or []
    dots = "".join(
        f'<i class="dot {signed_cls(v)}" title="{e(m)} {pct(v, 0)}"></i>' if v is not None else '<i class="dot"></i>'
        for m, v in series
    )
    return f'<span class="dots">{dots}</span>' if dots else "—"


def metric_cells(c: dict, style: str) -> list[str]:
    co = c.get("company") or {}
    if style == "value":
        return [pct(co.get("dividend_yield"), ratio=False), pct(co.get("roe")), num(co.get("pe"))]
    return [num(co.get("pe")), pct(co.get("gross_margin")), pct(co.get("roe"))]


METRIC_HEAD = {"value": ["殖利率", "ROE", "本益比"], "growth": ["本益比", "毛利率", "ROE"]}


def candidate_detail(c: dict) -> str:
    checks = "".join(
        f'<li class="{"ok" if ch["passed"] else "ng"}"><b>{e(ch["label"])}</b>{e(ch.get("detail"))}</li>'
        for ch in c.get("checks", [])
    )
    flags = "".join(f'<li class="flag"><b>紅旗</b>{e(f)}</li>' for f in c.get("flags", []))
    ld = c.get("leader") or {}
    leader = ""
    if ld and not ld.get("self"):
        leader = (f'<p class="leader">產業龍頭對照：<b>{e(ld.get("code"))} {e(ld.get("name"))}</b>'
                  f'　本益比 {num(ld.get("pe"))}・殖利率 {pct(ld.get("dividend_yield"), ratio=False)}'
                  f'・ROE {pct(ld.get("roe"))}・毛利率 {pct(ld.get("gross_margin"))}</p>')
    return f'<ul class="checks">{flags}{checks}</ul>{leader}'


def candidate_table(cands: list[dict], style: str, show_reason: bool = False, new_codes=()) -> str:
    if not cands:
        return '<p class="empty">目前沒有</p>'
    heads = "".join(f'<span class="num">{h}</span>' for h in METRIC_HEAD[style])
    rows = []
    for c in cands:
        cells = "".join(f'<span class="num">{v}</span>' for v in metric_cells(c, style))
        reason = ""
        if show_reason:
            missed = [ch["label"] for ch in c.get("checks", []) if not ch["passed"]]
            reason = f'<span class="why">{e("、".join(c.get("flags") or []) or "未通過：" + "、".join(missed))}</span>'
        rows.append(
            f'<details class="row"><summary>'
            f'<span class="name">{stock_logo(c.get("code"), c.get("name"), c.get("market"), "sm")}'
            f'<span><b>{e(c.get("name"))}</b>{'<span class="pill new">新進</span>' if c.get("code") in new_codes else ""}'
            f'<small>{e(c.get("code"))}・{e(c.get("industry"))}</small>{reason}</span></span>'
            f'{cells}<span class="num">{rev_dots(c)}</span>'
            f'{score_bar(c.get("n_pass") or 0, c.get("n_total") or 0)}</summary>'
            f'<div class="row-body">{candidate_detail(c)}</div></details>'
        )
    head = (f'<div class="thead"><span class="name">公司</span>{heads}'
            f'<span class="num">月營收年增</span><span class="score">符合</span></div>')
    return f'<div class="ctable">{head}{"".join(rows)}</div>'


def etf_table(etfs: list[dict]) -> str:
    if not etfs:
        return ""
    rows = "".join(
        f'<tr><td><span class="name">{stock_logo(x["id"], x["name"], None, "sm")}<span><b>{e(x["id"])}</b> {e(x["name"])}</span></span></td>'
        f'<td class="muted">{e(x.get("theme"))}</td>'
        f'<td class="num {signed_cls(x.get("ret_1y"))}">{pct(x.get("ret_1y"))}</td>'
        f'<td class="num">{pct(x.get("yield_ttm"))}</td>'
        f'<td class="num">{"✓" if x.get("above200") else "—"}</td></tr>'
        for x in etfs
    )
    return ('<div class="table-wrap"><table><thead><tr><th>ETF</th><th>主題</th><th class="num">近一年</th>'
            f'<th class="num">殖利率</th><th class="num">200 日線上</th></tr></thead><tbody>{rows}</tbody></table></div>')


def company_card(c: dict, prefix: str = "../") -> str:
    price = c.get("price") or {}
    val = c.get("valuation") or {}
    cur = "新台幣" if c.get("currency") == "TWD" else "美元"
    sections = parse_structured_summary((c.get("analysis") or {}).get("lead") or "")
    consensus = next((s for s in sections if s["header"] == "共識"), sections[0] if sections else None)
    takeaway = clip(strip_cites(consensus["items"][0]), 70) if consensus and consensus["items"] else ""
    body = "".join(
        f'<h4>{e(s["header"])}</h4><ul>' + "".join(f"<li>{e(strip_cites(it))}</li>" for it in s["items"]) + "</ul>"
        for s in sections
    )
    tag = '<span class="pill">篩選候選</span>' if c.get("from_screen") else ""
    bubbles = visuals.persona_bubbles_from_text((c.get("analysis") or {}).get("personas"), prefix)
    cover = revenue_bars(c.get("quarters"))
    cover = (f'<div class="co-cover">{cover}<small>近 {min(6, len(c.get("quarters") or []))} 季營收</small></div>' if cover
             else f'<div class="co-cover big-logo">{stock_logo(c.get("ticker"), c.get("name"), c.get("market"), "xl")}</div>')
    return (
        f'<article class="co">{cover}<div class="co-head">{stock_logo(c.get("ticker"), c.get("name"), c.get("market"), "sm")}'
        f'<div><b>{e(short_name(c.get("name")))}</b><small>{e(c.get("ticker"))}</small></div>{tag}</div>'
        f'<div class="co-stats"><div><small>股價（{cur}）</small>{num(price.get("price"), 2 if (price.get("price") or 0) < 1000 else 0)}</div>'
        f'<div><small>本益比</small>{num(val.get("pe_ttm"))}</div>'
        f'<div><small>FCF 殖利率</small>{pct(val.get("fcf_yield"))}</div></div>'
        + (f'<p class="lede">{e(takeaway)}</p>' if takeaway else "")
        + (f'<details class="more"><summary>四位投資人怎麼看</summary><div class="more-body">{bubbles}</div></details>' if bubbles else "")
        + (f'<details class="more"><summary>綜合分析（共識、分歧、三種情境）</summary><div class="more-body">{body}</div></details>' if body else "")
        + "</article>"
    )


def render_report_page(r: dict, prev_r, next_r) -> str:
    s = r["screen"]
    extra = f'<p class="hero-note">{DISCLAIMER}四位投資人角色為模擬框架。</p>'
    legacy = bool(s and "stocks" in s and "value" not in s)
    if legacy:
        n_c = sum(1 for x in s["stocks"] if x.get("candidate"))
        sub = f"全球龍頭供應鏈 {len(s['stocks'])} 檔 → {n_c} 檔符合多數條件"
        extra = funnel([("供應鏈公司", len(s["stocks"])), ("符合多數條件", n_c)]) + extra
    elif s and not screen_ok(s):
        sub = "本期全市場資料沒抓齊，篩選結果改看每日更新"
    elif s:
        counts = {st: bucket(s.get(st, [])) for st in STYLE_LABEL}
        n_full = sum(len(b["full"]) for b in counts.values())
        n_pre = sum((s.get("prefilter") or {}).values())
        sub = f'全市場 {s.get("n_market", "—")} 家 → 初篩 {n_pre} 家 → 完全符合 {n_full} 家'
        extra = funnel([("全市場上市櫃公司", s.get("n_market") or 0), ("通過初篩", n_pre),
                        ("完整檢查", sum(len(s.get(st, [])) for st in STYLE_LABEL)), ("完全符合", n_full)]) + extra
    else:
        sub = f"{len(r['companies'])} 家公司基本面分析"
    body = hero("每週研究", zh_date(r["date"]), sub, extra)
    body += '<main class="wrap">'

    if legacy:
        body += section("台股研究候選：全球龍頭供應鏈", legacy_screen(s), "依通過條件的比例排序")
    elif s and not screen_ok(s):
        body += section("台股研究候選", '<p class="empty">這一期執行時證交所、櫃買中心的全市場資料沒有抓齊（網路中斷），'
                        '為了不把「0 檔通過」誤當成結論，本期不列候選。<a href="index.html">看每個交易日更新的最新候選 →</a></p>')
    elif s:
        body += screen_sections(s)

    if r["companies"]:
        cards = "".join(company_card(c) for c in r["companies"])
        body += section("個股分析", f'<div class="co-grid">{cards}</div>')

    if r["md"]:
        body += f'<p class="full-link"><a href="{r["date"]}-full.html">看完整文字報告 →</a></p>'
    body += pager(prev_r and f"{prev_r['date']}.html", prev_r and prev_r["date"],
                  next_r and f"{next_r['date']}.html", next_r and next_r["date"], "index.html")
    return body + "</main>"


def screen_sections(s: dict, new: dict | None = None) -> str:
    out = ""
    for st, (label, horizon) in STYLE_LABEL.items():
        b = bucket(s.get(st, []))
        inner = candidate_table(b["full"], st, new_codes=(new or {}).get(st, ()))
        if b["near"]:
            inner += (f'<details class="fold"><summary>差一項（{len(b["near"])}）</summary>'
                      f'{candidate_table(b["near"], st, show_reason=True)}</details>')
        if b["flagged"]:
            inner += (f'<details class="fold"><summary>紅旗排除（{len(b["flagged"])}）</summary>'
                      f'{candidate_table(b["flagged"], st, show_reason=True)}</details>')
        out += section(f"{label}候選", inner, f"{horizon}・點列展開檢查細節")
    if s.get("etfs"):
        out += section("主題 ETF", etf_table(s["etfs"]))
    return out


def screen_stamp(ls: dict) -> str:
    if ls["source"] == "daily":
        t = ls.get("generated_at", "")
        return f"{zh_date(ls['date'])} {visuals.floor5(t)} 更新・每個交易日收盤後"
    return f"{zh_date(ls['date'])} 週報篩選"


def screen_changes(ls: dict) -> str:
    """跟上一個交易日比：新進榜、移出的公司。"""
    ch = ls.get("changes") or {}
    names = {c["code"]: c["name"] for st in STYLE_LABEL for c in ls.get(st, [])}
    rows = []
    for st, (label, _) in STYLE_LABEL.items():
        c = ch.get(st) or {}
        add = "、".join(f'{e(names.get(x, x))}' for x in c.get("added", []))
        rem = "、".join(e(names.get(x, x)) for x in c.get("removed", []))
        if add or rem:
            rows.append(f'<li><b>{label}</b>' + (f'<span class="up">＋ {add}</span>' if add else "")
                        + (f'<span class="down">－ {rem}</span>' if rem else "") + "</li>")
    since = next((c.get("since") for c in ch.values() if c and c.get("since")), None)
    if not since:
        return ""
    if not rows:
        return f'<p class="screen-diff muted">跟 {e(zh_date(since))} 比，完全符合名單沒有變動。</p>'
    return f'<ul class="screen-diff"><li class="muted">跟 {e(zh_date(since))} 比</li>{"".join(rows)}</ul>'


def latest_screen_block(ls: dict) -> str:
    """每週研究目錄最上面：最新一次的全市場篩選（每個交易日更新）。"""
    full = {st: bucket(ls.get(st, []))["full"] for st in STYLE_LABEL}
    n_pre = sum((ls.get("prefilter") or {}).values())
    n_full = sum(len(v) for v in full.values())
    new = {st: (ls.get("changes") or {}).get(st, {}).get("added", []) for st in STYLE_LABEL}
    head = (f'<div class="screen-live"><span class="live-dot"></span><b>最新研究候選</b><small>{e(screen_stamp(ls))}</small></div>'
            + funnel([("全市場上市櫃公司", ls.get("n_market") or 0), ("通過初篩", n_pre),
                      ("完整檢查", sum(len(ls.get(st, [])) for st in STYLE_LABEL)), ("完全符合", n_full)])
            + screen_changes(ls))
    return section("每日更新的研究候選", head, "篩選條件同每週報告；四框架深度分析仍每週三、每月 11 日各一次") + screen_sections(ls, new)


def render_full_report(r: dict) -> str:
    md = markdown.Markdown(extensions=["tables", "toc", "sane_lists"], extension_configs={"toc": {"toc_depth": "2-3"}})
    html_body = re.sub(r"^<h1[^>]*>.*?</h1>", "", md.convert(r["md"]), count=1, flags=re.S)
    toc = f'<details class="fold toc"><summary>目錄</summary>{md.toc}</details>' if md.toc_tokens else ""
    return (hero("每週研究・完整報告", zh_date(r["date"]), f'<a href="{r["date"]}.html">← 回到精簡版</a>')
            + f'<main class="wrap">{toc}<div class="prose">{html_body}</div></main>')


def home_candidates(s: dict | None) -> str:
    if not s:
        return '<p class="empty">目前沒有可用的台股篩選結果</p>'
    cols = []
    for st, (label, horizon) in STYLE_LABEL.items():
        full = bucket(s.get(st, []))["full"]
        new = set(((s.get("changes") or {}).get(st) or {}).get("added", []))
        items = "".join(
            f'<li>{stock_logo(c["code"], c["name"], c.get("market"), "sm")}<b>{e(c["name"])}</b>'
            f'{'<span class="pill new">新進</span>' if c["code"] in new else ""}<small>{e(c["code"])}・{e(c.get("industry"))}</small>'
            f'<span class="num">{metric_cells(c, st)[0]}</span></li>'
            for c in full
        ) or '<li class="empty">目前沒有</li>'
        cols.append(f'<div class="pick"><div class="pick-head">{label}<small>{horizon}・{METRIC_HEAD[st][0]}</small></div><ul>{items}</ul></div>')
    return f'<div class="picks">{"".join(cols)}</div>'


# ---------- 投資總覽 ----------

def money(x, signed=False) -> str:
    if x is None:
        return "—"
    return f"{x:+,.0f}" if signed else f"{x:,.0f}"


def signed_money(x) -> str:
    return f'<span class="{signed_cls(x)}">{money(x, signed=True)}</span>'


def signed_pct(x) -> str:
    return "—" if x is None else f'<span class="{signed_cls(x)}">{x * 100:+.1f}%</span>'


def shares_fmt(x) -> str:
    return "—" if x is None else f"{x:,.0f}"


def allocation_bar(alloc: list[tuple[str, float]], total: float) -> str:
    if not total:
        return ""
    segs = "".join(f'<i class="seg s{i % 5}" style="width:{v / total * 100:.2f}%"></i>' for i, (_, v) in enumerate(alloc))
    legend = "".join(
        f'<li><i class="sw s{i % 5}"></i>{e(name)}<b>{v / total * 100:.1f}%</b></li>' for i, (name, v) in enumerate(alloc)
    )
    return f'<div class="alloc"><div class="bar">{segs}</div><ul class="legend">{legend}</ul></div>'


def live_attrs(h: dict) -> str:
    """台股持股讓前端用盤中即時價重算市值與損益（site.js）。"""
    if not re.fullmatch(r"\d{4,6}[A-Z]?", h.get("code") or "") or not h.get("shares"):
        return ""
    return (f' data-live-tw="{e(h["code"])}" data-shares="{h["shares"]:g}" data-cost="{h.get("cost") or 0:g}"'
            f' data-value="{h.get("value") or 0:g}"')


def holdings_table(holdings: list[dict]) -> str:
    rows = "".join(
        f'<tr{live_attrs(h)}><td><span class="name">{stock_logo(h["code"], h["name"], None, "sm")}<span><b>{e(h["name"])}</b><small>{e(h["code"])}・<span data-f="pct"></span></small></span></span></td>'
        f'<td class="num">{shares_fmt(h["shares"])}</td>'
        f'<td class="num">{num(h["avg_cost"], 2)}</td>'
        f'<td class="num" data-f="price">{num(h["price"], 2)}</td>'
        f'<td class="num" data-f="value">{money(h["value"])}</td>'
        f'<td class="num" data-f="pl">{signed_money(h["unrealized"])}</td>'
        f'<td class="num" data-f="plpct">{signed_pct(h["return"])}</td>'
        f'<td class="num">{h["weight"] * 100:.1f}%</td></tr>'
        for h in holdings
    )
    return ('<div class="table-wrap"><table class="holdings"><thead><tr><th>標的</th><th class="num">股數</th>'
            '<th class="num">均價</th><th class="num">現價</th><th class="num">市值</th><th class="num">未實現損益</th>'
            f'<th class="num">報酬率</th><th class="num">占比</th></tr></thead><tbody>{rows}</tbody></table></div>')


def trade_line(t: dict) -> str:
    return (f'{e(t["date"])} {e(t.get("code") or "")} {e(t.get("name") or "")} {e(t["side"])} '
            f'{shares_fmt(t["quantity"])} 股 @ {num(t["price"], 2)}')


def reconcile_block(rc: dict) -> str:
    if not rc["months"]:
        return ('<div class="soon">還沒有券商對帳單資料。每月 6 日自動處理新對帳單；'
                '要補過去的月份，到 對帳單 repo 的 Actions 手動執行並勾選 include_read。</div>')
    last = rc["months"][-1]
    pos = rc["positions"]
    bad_pos = [p for p in pos if not p["ok"]]
    issues = portfolio.issue_count(rc)

    if not issues:
        status = (f'<div class="rc-status ok"><b>✓ 一致</b>{len(pos)} 檔持股股數與券商對帳單相符'
                  f'（對帳單 {rc["months"][0]} – {last}）</div>')
    else:
        status = f'<div class="rc-status ng"><b>{issues} 項不一致</b>對帳單 {rc["months"][0]} – {last}</div>'

    items = "".join(
        f'<li><span class="pill">股數不同</span>{e(p["code"])} {e(p["name"] or "")}：對帳單 {shares_fmt(p["broker"])} 股，'
        f'Notion {shares_fmt(p["notion"])} 股</li>' for p in bad_pos)
    for m in rc["mismatched"]:
        items += (f'<li><span class="pill">數字不同</span>券商：{trade_line(m["broker"])}'
                  f'<br><span class="muted">Notion：{trade_line(m["notion"])}</span></li>')
    for b in rc["broker_only"]:
        items += f'<li><span class="pill">Notion 漏記</span>{trade_line(b)}</li>'
    for n in rc["notion_only"]:
        items += f'<li><span class="pill">對帳單沒有</span>{trade_line(n)}</li>'

    rows = "".join(
        f'<tr><td><b>{e(p["name"] or "")}</b><small>{e(p["code"])}</small></td>'
        f'<td class="num">{shares_fmt(p["broker"])}</td><td class="num">{shares_fmt(p["notion"])}</td>'
        f'<td class="num {"" if p["ok"] else "pos"}">{"✓" if p["ok"] else "✕"}</td></tr>' for p in pos)
    table = ('<details class="fold"><summary>各檔股數對照</summary><div class="table-wrap"><table class="holdings">'
             '<thead><tr><th>標的</th><th class="num">對帳單累計</th><th class="num">Notion 庫存</th><th class="num"></th></tr></thead>'
             f'<tbody>{rows}</tbody></table></div></details>')
    trade_note = (f'<p class="rc-note">逐筆核對：Notion 從 {e(rc["opening"])} 開始記錄（該日為期初持股），'
                  f'之後的成交已比對 {rc["matched"]} 筆相符。</p>' if rc["opening"] else "")
    return status + (f'<ul class="rc-list">{items}</ul>' if items else "") + trade_note + table


def portfolio_tabs(active: str) -> str:
    tabs = [("overview", "/portfolio/", "持股總覽"), ("advisor", "/portfolio/advisor/", "AI 投資顧問")]
    return ('<div class="pf-tabs"><div class="wrap">' + "".join(
        f'<a href="{href}"{" class=\"on\"" if key == active else ""}>{label}</a>' for key, href, label in tabs) + "</div></div>")


def advisor_suggestions(sm: dict | None, picks: dict | None) -> list[str]:
    from supply_map import TW_PEERS

    out = []
    held = [h for h in (sm or {}).get("holdings", []) if h.get("code", "").isdigit() and len(h["code"]) == 4]
    if held:
        out.append(f'{short_name(held[0]["name"])} 還值得續抱嗎？')
        peer = next((p for h in held for p in TW_PEERS.get(h["code"], [])), None)
        if peer:
            owner = next(h for h in held if peer in TW_PEERS.get(h["code"], []))
            out.append(f'{short_name(owner["name"])} 和 {peer["name"]} 哪個比較值得投資？')
        out.append("我的持股有沒有太集中？")
    tw = next((p for p in (picks or {}).get("picks", []) if p.get("market") == "台股"), None)
    if tw:
        out.append(f'今日觀察的 {tw["name"]} 值得研究嗎？')
    out += ["台積電和聯電哪個比較值得投資？", "什麼是最大回撤和 VaR？"]
    seen = set()
    return [q for q in out if not (q in seen or seen.add(q))][:6]


def render_advisor_page(sm: dict | None, picks: dict | None, adv_meta: dict | None, guest: bool = False) -> str:
    body = (ROOT / "static" / "advisor_body.html").read_text(encoding="utf-8")
    chips = "".join(f'<button type="button" class="chip" data-q="{e(q)}">{e(q)}</button>' for q in advisor_suggestions(None if guest else sm, picks))
    if guest:
        body = (body.replace("{{KICKER}}", "專屬投資顧問").replace("{{API}}", "/robot/api/advisor").replace("{{HIST}}", "robot-history-v1")
                .replace("{{SCOPE}}", "成交值前 250 名、供應鏈、今日觀察、每週研究候選等；每人每天最多 10 題")
                .replace("{{TABS}}", ""))
    else:
        body = (body.replace("{{KICKER}}", "AI 投資顧問・只有你看得到").replace("{{API}}", "/portfolio/api/advisor").replace("{{HIST}}", "advisor-history-v1")
                .replace("{{SCOPE}}", "持股、供應鏈、成交值前 250 名等；問到其他股票會自動加入，隔天補上")
                .replace("{{TABS}}", portfolio_tabs("advisor")))
    return (body.replace("{{SUGGESTIONS}}", chips)
            .replace("{{DATA_DATE}}", e(visuals.floor5((adv_meta or {}).get("generated_at"), "%Y-%m-%d %H:%M") or "—"))
            .replace("{{PRICED}}", str(len((adv_meta or {}).get("price_codes", [])))))


def render_finder_page(adv_meta: dict | None, guest: bool) -> str:
    body = (ROOT / "static" / "finder_body.html").read_text(encoding="utf-8")
    body = body.replace("{{KICKER}}", "專屬投資顧問" if guest else "AI 投資顧問・只有你看得到")
    body = body.replace("{{API}}", "/robot/api/finder" if guest else "/portfolio/api/finder")
    body = body.replace("{{TABS}}", "" if guest else portfolio_tabs("advisor"))
    body = body.replace("{{SCOPE}}", "全市場上市櫃股票；跟「問個股」共用每人每天 10 題" if guest else "全市場上市櫃股票；你已持有的會標出來")
    return body.replace("{{DATA_DATE}}", e(visuals.floor5((adv_meta or {}).get("generated_at"), "%Y-%m-%d %H:%M") or "—"))


def render_portfolio_page(sm: dict | None, rc: dict | None, error: str | None, supply: dict | None = None,
                          market: dict | None = None, whales: dict | None = None) -> str:
    if sm is None:
        body = hero("投資總覽", "暫時讀不到 Notion", e(error or ""))
        return body + '<main class="wrap"><div class="soon">設定好 NOTION_TOKEN 並把「股票交易管理」分享給 integration 後，下次重建就會出現。</div></main>'

    sub = (f'未實現損益 {signed_money(sm["unrealized"])}（{signed_pct(sm["unrealized_pct"])}）'
           f'・股價日期 {e(sm["price_date"] or "—")}・<a href="__logout">登出</a>'
           '<span class="pf-live" id="pf-live" hidden></span>')
    body = hero("投資總覽・市值（新台幣）", money(sm["total_value"]), sub)
    body += portfolio_tabs("overview")
    body += '<main class="wrap">'
    tiles = [("持有成本", money(sm["total_cost"]), "含手續費與稅"),
             ("未實現損益", signed_money(sm["unrealized"]), signed_pct(sm["unrealized_pct"])),
             ("已實現損益", signed_money(sm["realized"]), "含已出清標的"),
             ("累計實領配息", money(sm["dividends_total"]), f'{len(sm["recent_dividends"]) and "最近：" + e(sm["recent_dividends"][0]["date"]) or ""}')]
    body += section("損益概況", '<div class="stats">' + "".join(
        f'<div class="stat"><div class="stat-label">{label}</div><div class="stat-value">{value}</div>'
        f'<div class="stat-foot"><span>{foot}</span></div></div>' for label, value, foot in tiles) + "</div>")
    body += section("資產配置", allocation_bar(sm["allocation"], sm["total_value"]), "依 Notion「市場」分類")
    body += section("持股明細", holdings_table(sm["holdings"]) if sm["holdings"] else '<p class="empty">目前沒有持股</p>',
                    f'{len(sm["holdings"])} 檔')
    if whales:
        import whales_page
        body += section("我的持股 × 大佬", whales_page.holdings_whales(sm["holdings"], whales),
                        "你的持股是哪些大佬持有之美股龍頭的供應商（只有你看得到）", ("../whales/index.html", "看大佬持股"))
    if market:
        import market_page
        body += section("持股提醒", market_page.holdings_alerts(sm["holdings"], market), "處置／注意股・近期除權息（只有你看得到）")
    if supply:
        import supply_page
        body += section("我的持股 × 供應鏈", supply_page.holdings_exposure(sm["holdings"], supply),
                        "只有你看得到（在密碼保護的投資頁裡）", ("../supply/index.html", "看完整供應鏈地圖"))
    if rc is not None:
        body += section("對帳", reconcile_block(rc), "Notion 交易紀錄 × 券商對帳單")
    recent = "".join(f'<li><span class="pill">{e(t["side"])}</span>{trade_line(t)}</li>' for t in sm["recent_trades"])
    divs = "".join(f'<li><span class="pill">配息</span>{e(d["date"])} {e(d["name"] or "")}　<b>{money(d["amount"])}</b>'
                   f'<small>（每股 {num(d["per_share"], 2)}）</small></li>' for d in sm["recent_dividends"])
    body += ('<div class="two-col">'
             + section("近期交易", f'<ul class="feed">{recent}</ul>' if recent else '<p class="empty">尚無</p>')
             + section("近期配息", f'<ul class="feed">{divs}</ul>' if divs else '<p class="empty">尚無</p>')
             + "</div>")
    return body + "</main>"


def home_link_card(href: str, icon: str, title: str, sub: str, go: str) -> str:
    return (f'<a class="locked" href="{href}"><span class="lock">{icon}</span>'
            f'<span><b>{title}</b><small>{sub}</small></span><span class="go">{go} →</span></a>')


def legacy_screen(s: dict) -> str:
    """早期週報的「全球龍頭供應鏈」篩選：依通過比例排序的簡單清單。"""
    rows = "".join(
        f'<tr><td><span class="name">{stock_logo(x["id"], x["name"], None, "sm")}<span><b>{e(x["name"])}</b>'
        f'<small>{e(x["id"])}・{e(x.get("role") or "")}</small></span></span></td>'
        f'<td class="num">{score_bar(x.get("n_pass") or 0, x.get("n_total") or 0)}</td>'
        f'<td class="num">{"✓ 研究候選" if x.get("candidate") else ""}</td></tr>'
        for x in sorted(s.get("stocks", []), key=lambda x: -(x.get("ratio") or 0)))
    return ('<div class="table-wrap"><table class="holdings"><thead><tr><th>公司</th><th class="num">符合條件</th><th class="num"></th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def report_headline(r: dict) -> tuple[str, str, list[dict]]:
    """每週研究目錄卡的大標題、副標與要放 logo 的公司。"""
    s = r["screen"]
    companies = r["companies"]
    if s and "stocks" in s and "value" not in s:  # 早期的「全球龍頭供應鏈」篩選格式
        cands = [x for x in s["stocks"] if x.get("candidate")]
        names = "、".join(x["name"] for x in cands[:3])
        title = f"{names}等 {len(cands)} 檔供應鏈公司符合多數條件" if cands else "全球龍頭供應鏈篩選"
        sub = f"全球龍頭供應鏈 {len(s['stocks'])} 檔篩選｜{len(companies)} 家個股深度分析"
        logos = [{"code": x["id"], "name": x["name"], "market": None} for x in cands]
    elif s and not screen_ok(s):
        names = "、".join(short_name(c.get("name")) for c in companies[:3])
        title = f"{names}等 {len(companies)} 家個股深度分析" if companies else "本期篩選資料不完整"
        sub = "本期全市場資料沒抓齊，研究候選請看上方每日更新"
        logos = []
    elif s:
        full = [c for st in STYLE_LABEL for c in bucket(s.get(st, []))["full"]]
        names = "、".join(c["name"] for c in full[:3])
        title = f"{names}等 {len(full)} 檔通過全部篩選條件" if full else "本週沒有公司通過全部篩選條件"
        counts = "・".join(f"{label} {len(bucket(s.get(st, []))['full'])} 檔" for st, (label, _) in STYLE_LABEL.items())
        sub = f"全市場 {s.get('n_market', '—')} 家篩選｜{counts}｜{len(companies)} 家個股深度分析"
        logos = [{"code": c["code"], "name": c["name"], "market": c.get("market")} for c in full]
    else:
        names = "、".join(short_name(c.get("name")) for c in companies[:2])
        title = f"{names}等 {len(companies)} 家公司的基本面體檢"
        sub = "四位投資人框架逐家分析財務品質、估值與風險"
        logos = []
    logos += [{"code": c.get("ticker"), "name": c.get("name"), "market": c.get("market")} for c in companies
              if c.get("ticker") not in {x["code"] for x in logos}]
    return title, sub, logos


def digest_cover(d: dict) -> str:
    """每日總經封面：Q 版主題角色（當天新聞最多的主題當主角），取代畫質不好的新聞照片。"""
    return icons.digest_cover(d)


def fred_highlight(d: dict) -> str:
    """當天變動最大的一項 FRED 數據（依變動百分比）。"""
    best = None
    for r in d.get("fred", []):
        try:
            a, b = float(r["latest_value"]), float(r["previous_value"])
        except (TypeError, ValueError, KeyError):
            continue
        ch = (a - b) / b if b else 0
        if best is None or abs(ch) > abs(best[2]):
            best = (re.sub(r"\s*\(.*\)$", "", r["label"]), a, ch, a - b)
    if not best:
        return ""
    label, a, ch, diff = best
    arrow = "▲" if diff > 0 else "▼" if diff < 0 else "–"
    return f"{label} {a:,.2f}（{arrow}{abs(diff):,.2f}）"


def daily_index(digests: list[dict]) -> str:
    body = hero("每日總經", "歷史摘要", "每天早上 7 點更新：台股、國際頭條、工商時報摘要與美國總經數據")
    body += '<main class="wrap">'
    if not digests:
        return body + '<p class="empty">尚無資料</p></main>'
    cards = []
    for i, d in enumerate(digests):
        t_file = ROOT / "data" / "digest_titles" / f'{d["date"]}.json'
        title = json.loads(t_file.read_text(encoding="utf-8")) if t_file.exists() else {}
        secs = [(s.get("name"), len(s.get("articles", []))) for s in d.get("news_sections", []) if s.get("articles")]
        total = sum(n for _, n in secs)
        headline = title.get("headline") or next((a.get("title") for s in d.get("news_sections", []) for a in s.get("articles", [])), "每日總經摘要")
        sub = "・".join(f"{e(n)} {c}" for n, c in secs)
        fh = fred_highlight(d)
        tags = "".join(f'<span>#{e(t)}</span>' for t in title.get("tags", []))
        cards.append(
            f'<a class="rcard{" latest" if i == 0 else ""}" href="{d["date"]}.html">'
            f'<div class="rart">{digest_cover(d)}<span class="rdate">{e(zh_date(d["date"]))}</span>'
            f'<span class="rcount">{total} 則</span>{"<span class=rnew>最新</span>" if i == 0 else ""}</div>'
            f'<div class="rbody"><h3>{e(headline)}</h3><p>{sub}{"｜" + e(fh) if fh else ""}</p>'
            f'{f"<div class=kws>{tags}</div>" if tags else ""}</div></a>')
    body += section("全部摘要", f'<div class="rgrid">{"".join(cards)}</div>', f"{len(digests)} 天")
    return body + "</main>"


def weekly_index(reports: list[dict], ls: dict | None = None) -> str:
    body = hero("每週研究", "研究候選與歷史報告",
                "研究候選每個交易日收盤後更新；四位投資人框架的深度分析每週三、每月 11 日（月營收公布後）各一次")
    body += '<main class="wrap">'
    if ls:
        body += latest_screen_block(ls)
    if not reports:
        return body + '<p class="empty">尚無資料</p></main>'
    cards = []
    for i, r in enumerate(reports):
        title, sub, logos = report_headline(r)
        hue = (int(r["date"].replace("-", "")) * 37) % 360
        logo_row = "".join(stock_logo(x["code"], x["name"], x["market"], "sm") for x in logos[:8])
        more = f'<span class="more-n">+{len(logos) - 8}</span>' if len(logos) > 8 else ""
        cards.append(
            f'<a class="rcard{" latest" if i == 0 else ""}" href="{r["date"]}.html">'
            f'<div class="rart">{visuals.report_art(r["date"], len(logos), hue)}'
            f'<span class="rdate">{e(zh_date(r["date"]))}</span>{"<span class=rnew>最新</span>" if i == 0 else ""}</div>'
            f'<div class="rbody"><h3>{e(title)}</h3><p>{e(sub)}</p><div class="logos">{logo_row}{more}</div></div></a>')
    body += section("深度分析報告", f'<div class="rgrid">{"".join(cards)}</div>', f"{len(reports)} 份")
    body += section("四位投資人", visuals.investors_section("../"), "每份報告都用他們的框架分析", ("../investors/index.html", "完整介紹"))
    return body + "</main>"


# ---------- 組裝 ----------

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def date_index(kicker: str, title: str, items: list[tuple[str, str, str]]) -> str:
    body = hero(kicker, title)
    if not items:
        return body + '<main class="wrap"><p class="empty">尚無資料</p></main>'
    cards = "".join(f'<a class="date-card" href="{href}"><b>{e(label)}</b><small>{e(sub)}</small></a>' for href, label, sub in items)
    return body + f'<main class="wrap"><div class="date-grid">{cards}</div></main>'


def main() -> int:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    shutil.copy(ROOT / "static" / "style.css", OUT_DIR / "style.css")
    shutil.copy(ROOT / "static" / "_headers", OUT_DIR / "_headers")
    shutil.copy(ROOT / "static" / "sim.js", OUT_DIR / "sim.js")
    sim_body = (ROOT / "static" / "sim_body.html").read_text(encoding="utf-8")
    shutil.copy(ROOT / "static" / "site.js", OUT_DIR / "site.js")
    (OUT_DIR / "topics.js").write_text(icons.topics_js(), encoding="utf-8")
    import glossary
    (OUT_DIR / "glossary.js").write_text(glossary.to_js(), encoding="utf-8")
    write(OUT_DIR / "news" / "index.html", page("即時快報", (ROOT / "static" / "news_body.html").read_text(encoding="utf-8"), 1, "news/index.html"))
    write(OUT_DIR / "sim" / "index.html", page("模擬交易", sim_body, 1, "sim/index.html"))

    import supply_page
    supply = supply_page.load(ROOT / "data" / "supply" / "latest.json")
    import market_page
    market = market_page.load(ROOT / "data" / "market" / "latest.json")
    import whales_page
    whales = whales_page.load(ROOT / "data" / "whales" / "latest.json")
    trump = whales_page.load(ROOT / "data" / "whales" / "trump.json")
    write(OUT_DIR / "whales" / "index.html", page("大佬持股", whales_page.render(whales, supply, hero, section, trump), 1, "whales/index.html"))
    write(OUT_DIR / "market" / "index.html", page("台股", market_page.render(market, hero, section, {**(market_page.load(ROOT / "data" / "market" / "extra.json") or {}),
                                                        "breadth": market_page.load(ROOT / "data" / "market" / "breadth.json")}), 1, "market/index.html"))
    import pick_page
    picks_all = pick_page.load_all(ROOT / "data" / "daily_pick")
    for i, pk in enumerate(picks_all):
        body_pk = (hero("每日一檔", pk["date"], "每天一檔台股：從發展歷史、產業位置講到未來前景，專有名詞都附資料來源。")
                   + f'<main class="wrap">{pick_page.article(pk)}'
                   + section("過去的每日一檔", pick_page.archive(picks_all[:30], pk["date"])) + "</main>")
        write(OUT_DIR / "pick" / f"{pk['date']}.html", page(f"每日一檔 {pk['name']}", body_pk, 1, "pick/index.html"))
        if i == 0:
            write(OUT_DIR / "pick" / "index.html", page("每日一檔", body_pk, 1, "pick/index.html"))
            # LINE 機器人有人打「今日一檔」時回覆用（functions/api/line/webhook.js 讀這個檔）
            import daily_pick
            (OUT_DIR / "pick" / "latest_line.json").write_text(json.dumps(
                {"date": pk["date"], "messages": daily_pick.line_messages(pk)}, ensure_ascii=False), encoding="utf-8")
    if not picks_all:
        write(OUT_DIR / "pick" / "index.html", page("每日一檔", hero("每日一檔", "準備中", "第一篇明天早上 9 點前產生。"), 1, "pick/index.html"))
    import fx_page
    write(OUT_DIR / "fx" / "index.html", page("匯率", fx_page.render(market, hero, section), 1, "fx/index.html"))
    import us_page
    us_data = market_page.load(ROOT / "data" / "us" / "latest.json")
    write(OUT_DIR / "us" / "index.html", page("美股", us_page.render(us_data, hero, section, datetime.now(TAIPEI).strftime("%Y-%m-%d")), 1, "us/index.html"))
    # 公開資料出口（朋友串 Discord 用）：只放公開資料，不含任何站長相關資訊
    import feed
    import daily_pick
    feed.write_all(OUT_DIR / "feed", picks_all, daily_pick.line_messages, market,
                   market_page.load(ROOT / "data" / "market" / "extra.json"), us_data)

    digests = load_digests()  # 新 → 舊
    for i, d in enumerate(digests):
        older = digests[i + 1] if i + 1 < len(digests) else None
        newer = digests[i - 1] if i > 0 else None
        write(OUT_DIR / "daily" / f"{d['date']}.html", page(f"每日總經 {d['date']}", render_digest_page(d, older, newer), 1, "daily/index.html"))
    write(OUT_DIR / "daily" / "index.html", page("每日總經", daily_index(digests), 1, "daily/index.html"))

    reports = load_reports()
    latest_screen = load_latest_screen(reports)
    for i, r in enumerate(reports):
        older = reports[i + 1] if i + 1 < len(reports) else None
        newer = reports[i - 1] if i > 0 else None
        write(OUT_DIR / "weekly" / f"{r['date']}.html", page(f"每週研究 {r['date']}", render_report_page(r, older, newer), 1, "weekly/index.html"))
        if r["md"]:
            write(OUT_DIR / "weekly" / f"{r['date']}-full.html", page(f"完整報告 {r['date']}", render_full_report(r), 1, "weekly/index.html"))
    write(OUT_DIR / "weekly" / "index.html", page("每週研究", weekly_index(reports, latest_screen), 1, "weekly/index.html"))
    shutil.copytree(ROOT / "static" / "portraits", OUT_DIR / "portraits")
    shutil.copytree(ROOT / "static" / "ui", OUT_DIR / "ui")
    write(OUT_DIR / "supply" / "index.html", page("供應鏈地圖", supply_page.render(supply), 1, "supply/index.html"))
    write(OUT_DIR / "investors" / "index.html", page("四位投資人", hero(
        "四位投資人", "段永平・巴菲特・芒格・李錄",
        "本站的每週研究與今日觀察，都用這四位投資人的框架從四個角度看同一家公司。")
        + f'<main class="wrap">{section("他們是誰、為什麼值得參考", visuals.investors_section("../"))}'
        + (section("他們實際持有什麼", "".join(whales_page.manager_block(m) for m in whales["managers"] if m.get("investor")),
                   "SEC 13F 官方申報（真實持股，不是 AI 模擬）", ("../whales/index.html", "看十位大佬"))
           if whales else "") + '</main>', 1, "weekly/index.html"))

    # 投資總覽：讀不到 Notion 時照樣產生其他頁面
    sm = rc = err = None
    try:
        nd = portfolio.load_notion()
        sm = portfolio.summarize(nd)
        rc = portfolio.reconcile(portfolio.load_statements(STATEMENT_DIR), nd["trades"], nd["tickers"])
    except portfolio.NotionUnavailable as exc:
        err = str(exc)
        print(f"⚠️ 投資總覽略過：{exc}", file=sys.stderr)
    write(OUT_DIR / "portfolio" / "index.html", page("投資總覽", render_portfolio_page(sm, rc, err, supply, market, whales), 1, "portfolio/index.html"))

    # AI 投資顧問（同樣在 /portfolio/ 密碼後面）：每日資料 + 持股權重（只放比例，不放金額）
    adv_dir = OUT_DIR / "portfolio" / "advisor"
    adv_dir.mkdir(parents=True, exist_ok=True)
    adv_meta = None
    adv_src = ROOT / "data" / "advisor" / "stocks.json"
    if adv_src.exists():
        meta = visuals.clean_names(json.loads(adv_src.read_text(encoding="utf-8")))
        (adv_dir / "stocks.json").write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        adv_meta = {"generated_at": meta["generated_at"], "price_codes": meta["price_codes"]}
    if sm:
        (adv_dir / "holdings.json").write_text(json.dumps({"as_of": sm["price_date"], "holdings": [
            {"code": h["code"], "name": h["name"], "market": h["market"], "weight_pct": round(h["weight"] * 100, 1),
             "pl_pct": round(h["return"] * 100, 1) if h["return"] is not None else None} for h in sm["holdings"]]},
            ensure_ascii=False), encoding="utf-8")
    shutil.copy(ROOT / "static" / "advisor.js", adv_dir / "advisor.js")
    write(adv_dir / "index.html", page("AI 投資顧問", render_advisor_page(sm, visuals.load_latest_picks(PICKS_DIR), adv_meta), 2, "portfolio/index.html"))
    (adv_dir / "find").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "static" / "finder.js", adv_dir / "find" / "finder.js")
    write(adv_dir / "find" / "index.html", page("幫我找股票", render_finder_page(adv_meta, False), 3, "portfolio/index.html"))

    # 專屬投資顧問（訪客版，/robot/，所有登入網站的人都能用）：同一份每日資料，但只有「公開範圍」的股票保留風控與回測，
    # 只因為站長持股或站長提問才被計算的股票，降級成跟其他股票一樣，避免從範圍反推持股
    robot_dir = OUT_DIR / "robot"
    robot_dir.mkdir(parents=True, exist_ok=True)
    robot_meta = None
    if adv_src.exists():
        full = meta
        public = set(full.get("public_codes") or [])
        priced = set(full["price_codes"])
        base_keys = set().union(*(s.keys() for c, s in full["stocks"].items() if c not in priced))
        guest = {**full, "price_codes": sorted(public & priced), "stocks": {
            c: (s if c in public or c not in priced else {k: v for k, v in s.items() if k in base_keys})
            for c, s in full["stocks"].items()}}
        guest.pop("public_codes", None)
        (robot_dir / "stocks.json").write_text(json.dumps(guest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        # 公開資料出口也放同一份（訪客版已經不含持股與提問清單，見上面）
        (OUT_DIR / "feed").mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "feed" / "stocks.json").write_text(json.dumps(guest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        robot_meta = {"generated_at": full["generated_at"], "price_codes": guest["price_codes"]}
    shutil.copy(ROOT / "static" / "advisor.js", robot_dir / "advisor.js")
    write(robot_dir / "index.html", page("專屬投資顧問", render_advisor_page(None, visuals.load_latest_picks(PICKS_DIR), robot_meta, guest=True), 1, "robot/index.html"))
    (robot_dir / "find").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "static" / "finder.js", robot_dir / "find" / "finder.js")
    write(robot_dir / "find" / "index.html", page("幫我找股票", render_finder_page(robot_meta, True), 2, "robot/index.html"))

    # 總覽
    today = datetime.now(TAIPEI).strftime("%Y-%m-%d")
    picks = visuals.load_latest_picks(PICKS_DIR)
    body = hero("總覽", zh_date(today), "本日市場速報、今日觀察、即時快報與研究候選，一頁看完。")
    body += '<main class="wrap">'
    if market:
        extras = []
        if latest_screen:
            names = {c["code"]: c["name"] for st in STYLE_LABEL for c in latest_screen.get(st, [])}
            added = [names.get(x, x) for st in STYLE_LABEL
                     for x in ((latest_screen.get("changes") or {}).get(st) or {}).get("added", [])]
            n_full = sum(len(bucket(latest_screen.get(st, []))["full"]) for st in STYLE_LABEL)
            extras.append(("研究候選", f"完全符合 {n_full} 檔" + (f"，新進：{e('、'.join(added))}" if added else "，名單沒有變動"),
                           "weekly/index.html"))
        if digests:
            d0 = digests[0]
            top = next((a.get("title") for sec in d0.get("news_sections", []) for a in sec.get("articles", [])), None)
            if top:
                extras.append(("早報頭條", e(top), f"daily/{d0['date']}.html"))
        body += section("本日市場速報", market_page.brief(market, extras, today), "收盤數字自動整理・不是投資建議",
                        ("market/index.html", "看完整市場"))
    if picks_all:
        body += section("每日一檔", pick_page.home_card(picks_all[0]), "每天早上 9 點更新・研究素材，不是買賣建議",
                        ("pick/index.html", "看過去的推薦"))
    body += section("今日觀察", visuals.observations(picks, ""),
                    f"段永平・巴菲特・芒格・李錄的框架・{e(picks['date'])} 產生" if picks else "", ("investors/index.html", "認識四位投資人"))
    if supply and supply.get("leaders"):
        top = max(supply["leaders"], key=lambda l: l.get("chg_1d") or 0)
        chain = sorted((t for t in supply["tw"] if top["code"] in t["links"]), key=lambda t: -(t.get("chg_1d") or 0))[:4]
        names = "、".join(f'{t["name"]} {t["chg_1d"]:+.1f}%' for t in chain)
        body += section("供應鏈連動", home_link_card("supply/index.html", ui("chain", "/"),
                        f'本日最強：{e(top["name"])}（{e(top["market"])}）{top["chg_1d"]:+.2f}%',
                        f'台股相關：{e(names)}' if names else "看看台股供應鏈怎麼反應", "看供應鏈地圖"))
    if market and market.get("indices"):
        tw = market["indices"][0]
        b = market["breadth"]
        hot = max(market.get("industries", [])[:15] or [{"name": "—", "pct": 0}], key=lambda g: g["pct"])
        body += section("台股", home_link_card("market/index.html", ui("map", "/"),
                        f'{e(tw["name"])} {tw["close"]:,.0f}（{tw["chg_pct"]:+.2f}%）・上漲 {b["up"]} 家／下跌 {b["down"]} 家',
                        f'最強產業：{e(hot["name"])} {hot["pct"]:+.2f}%・處置／注意股 {len(market.get("warnings", []))} 檔',
                        "看熱力圖"))
    if whales and whales.get("by_ticker"):
        top = sorted(whales["by_ticker"].values(), key=lambda t: (-t["buying"], -t["n"]))[:3]
        body += section("大佬持股", home_link_card("whales/index.html", ui("whale", "/"),
                        f'{len(whales["managers"])} 位大佬最新 13F：本季最多人買進 ' + "、".join(e(t["ticker"]) for t in top),
                        "巴菲特、段永平、李錄、Ackman…持股與台股供應鏈連動", "看大佬在買什麼"))
    body += section("即時快報", '<ol class="headlines live" id="live-ticker"><li class="empty">讀取中…</li></ol>',
                    '<span class="live-dot"></span>每 3 分鐘更新', ("news/index.html", "看全部快報"))
    body += section("專屬投資顧問", home_link_card("robot/index.html", ui("rocket", "/"), "想跟 AI 討論股票？直接問就好",
                                                  "風控派 vs 回測派辯論，再給融合後的看法・每人每天 10 題", "開始討論"))
    # 首頁所有登入者都看得到，持股數字只放在有密碼的 /portfolio/
    body += section("我的投資", home_link_card("portfolio/index.html", ui("lock", "/"), "投資總覽需要密碼",
                                               "持股、損益與對帳結果只給站長本人看", "輸入密碼"))
    if digests:
        d = digests[0]
        body += section("美國總經數據", fred_tiles(d.get("fred", [])), f"FRED・{d['date']}")
        body += section("今日頭條", headline_list(d, 6, ""), "", (f"daily/{d['date']}.html", "看全部摘要"))
    else:
        body += section("每日總經", '<p class="empty">第一份每日摘要產生後會出現在這裡</p>')
    if latest_screen:
        body += section("研究候選", home_candidates(latest_screen), f"{screen_stamp(latest_screen)}・完全符合條件",
                        ("weekly/index.html", "看完整名單"))
    body += section("模擬交易", home_link_card("sim/index.html", ui("chart", "/"), "用 100 萬虛擬資金練習下單",
                                               "台股上市櫃與 ETF，跟朋友比排行榜", "開始"))
    body += "</main>"
    write(OUT_DIR / "index.html", page("總覽", body, 0, "index.html"))

    # log 只印筆數，不印金額（Actions log 雖然是 private，也不放持股數字）
    pf = f"{len(sm['holdings'])} 檔持股" if sm else "投資總覽略過"
    rcs = (f"對帳 {len(rc['months'])} 個月、{len(rc['positions'])} 檔持股、不一致 {portfolio.issue_count(rc)} 項"
           if rc else "未對帳")
    print(f"✅ 產生 {len(digests)} 份每日總經、{len(reports)} 份每週研究、{pf}、{rcs} → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
