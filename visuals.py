"""
網頁上的小圖與視覺元件：走勢迷你圖、季營收長條、篩選漏斗、今日觀察卡、新聞封面。
全部是內嵌 SVG／HTML，不依賴外部圖表套件；顏色用 CSS 變數，深淺色模式自動切換。
"""

import html
import json
import re
from pathlib import Path

from picks import METRIC_LABELS

STANCE_CLASS = {"偏多": "bull", "中性": "flat", "保留": "bear"}


def e(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


# ---------- 小圖 ----------

def sparkline(values: list[float] | None, w: int = 240, h: int = 64, cls: str = "") -> str:
    """60 日收盤價走勢：線＋漸層面積＋最後一點；漲跌決定顏色（紅漲綠跌）。"""
    vals = [v for v in (values or []) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pts = [(i * (w - 4) / (len(vals) - 1) + 2, h - 4 - (v - lo) / span * (h - 8)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"2,{h} " + line + f" {pts[-1][0]:.1f},{h}"
    tone = "pos" if vals[-1] >= vals[0] else "neg"
    gid = f"g{abs(hash((tuple(vals), w))) % 10**8}"
    lx, ly = pts[-1]
    return (f'<svg class="spark {tone} {cls}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="currentColor" stop-opacity=".28"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/>'
            f'</linearGradient></defs><polygon points="{area}" fill="url(#{gid})"/>'
            f'<polyline class="draw" points="{line}" fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="currentColor"/></svg>')


def revenue_bars(quarters: list[dict] | None, w: int = 240, h: int = 70) -> str:
    qs = [q for q in (quarters or []) if q.get("revenue")][-6:]
    if len(qs) < 2:
        return ""
    top = max(q["revenue"] for q in qs)
    bw = (w - 8) / len(qs)
    bars = "".join(
        f'<rect class="bar" style="--i:{i}" x="{4 + i * bw + bw * .18:.1f}" y="{h - 14 - q["revenue"] / top * (h - 20):.1f}" '
        f'width="{bw * .64:.1f}" height="{q["revenue"] / top * (h - 20):.1f}" rx="2"/>'
        f'<text x="{4 + i * bw + bw / 2:.1f}" y="{h - 2}" text-anchor="middle">{e(q["end"][2:7].replace("-", "/"))}</text>'
        for i, q in enumerate(qs))
    return f'<svg class="revbars" viewBox="0 0 {w} {h}" aria-label="近 {len(qs)} 季營收">{bars}</svg>'


def monogram(text: str, seed: str) -> str:
    """沒有圖可放時的封面：取名稱第一個字，背景色由代號決定（同一家每次一樣）。"""
    hue = sum(map(ord, seed)) % 360
    return f'<div class="mono" style="--h:{hue}">{e((text or "?")[:1])}</div>'


def news_cover(a: dict, section_name: str) -> str:
    if a.get("thumb"):
        return f'<img class="cover" src="{e(a["thumb"])}" alt="" loading="lazy" referrerpolicy="no-referrer">'
    tag = next((k for k in a.get("keywords") or [] if len(k) <= 6), section_name)
    hue = sum(map(ord, a.get("title") or "x")) % 360
    return f'<div class="cover gen" style="--h:{hue}"><span>{e(tag)}</span></div>'


def funnel(steps: list[tuple[str, int]]) -> str:
    """篩選漏斗：寬度用對數比例，讓 1982 → 8 這種差距也看得到每一層。"""
    import math
    top = math.log10(max(steps[0][1], 10))
    rows = "".join(
        f'<div class="fstep" style="--w:{max(12, math.log10(max(n, 1)) / top * 100):.0f}%;--i:{i}">'
        f'<span class="fbar"></span><b data-count>{n:,}</b><small>{e(label)}</small></div>'
        for i, (label, n) in enumerate(steps))
    return f'<div class="funnel">{rows}</div>'


def score_bar(n_pass: int, n_total: int) -> str:
    pct = n_pass / n_total * 100 if n_total else 0
    return f'<span class="score"><i style="--p:{pct:.0f}%"></i><b>{n_pass}/{n_total}</b></span>'


# ---------- 今日觀察 ----------

def load_latest_picks(picks_dir: Path) -> dict | None:
    files = sorted(picks_dir.glob("*.json")) if picks_dir.is_dir() else []
    return clean_names(json.loads(files[-1].read_text(encoding="utf-8"))) if files else None


def _metric_chip(key: str, value) -> str:
    label, unit, note = METRIC_LABELS[key]
    if isinstance(value, bool):
        shown = "是" if value else "否"
    elif isinstance(value, float):
        shown = f"{value:,.2f}" if abs(value) < 10 else f"{value:,.1f}"
        shown += unit
    else:
        shown = f"{value:,}{unit}" if isinstance(value, int) else f"{value}{unit}"
    tone = ""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and key.endswith(("pct", "lots_5d", "100m")):
        tone = "pos" if value > 0 else "neg" if value < 0 else ""
    return f'<li title="{e(note)}"><small>{e(label)}</small><b class="{tone}">{e(shown)}</b></li>'


KEY_METRICS = {
    "台股": ["net_value_5d_100m", "buy_days_5d", "industry_rank", "rev_m_yoy_pct", "pe", "ret_20d_pct"],
    "美股": ["sector_rel_20d_pct", "cmf_20", "vol_ratio_5_50", "ret_20d_pct", "pe", "from_52w_high_pct"],
}


def floor5(iso: str | None, fmt: str = "%H:%M") -> str:
    """網站上顯示的「更新於」時間一律往下取到 5 分鐘整（21:07 → 21:05），不顯示秒。"""
    from datetime import datetime
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    return d.replace(minute=d.minute - d.minute % 5, second=0, microsecond=0).strftime(fmt)


def clean_name(name):
    """證交所／櫃買的股名有時帶「*」（例如「國巨*」，官方用來標示面額不是 10 元的公司），網站上一律拿掉。"""
    return name.replace("*", "").strip() if isinstance(name, str) else name


def clean_names(obj):
    """把整份 JSON 裡所有 "name" 欄位的「*」拿掉（讀進來的舊資料也一併清掉）。"""
    if isinstance(obj, dict):
        return {k: clean_name(v) if k == "name" else clean_names(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_names(x) for x in obj]
    return obj


def short_name(name: str) -> str:
    """Advanced Micro Devices, Inc. → Advanced Micro Devices"""
    return re.sub(r",?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Ltd\.?|plc|Co\.?|Company|COM INC)$", "", clean_name(name or ""), flags=re.I).strip()


def observation_card(p: dict, prefix: str = "") -> str:
    m = p.get("metrics", {})
    chips = "".join(_metric_chip(k, m[k]) for k in KEY_METRICS[p["market"]] if m.get(k) is not None)
    v = p.get("views") or {}
    personas = "".join(
        bubble(x["role"], prefix, f'<p>{e(x["text"])}</p>', x["stance"]) if x.get("role") in BY_ID else
        f'<div class="persona"><b>{e(x["name"])}</b><p>{e(x["text"])}</p></div>'  # 舊格式（改版前的角色）
        for x in v.get("views", []))
    watch = "".join(f"<li>{e(w)}</li>" for w in v.get("watch", []))
    news = "".join(f'<li><a href="{e(n["url"])}" target="_blank" rel="noopener">{e(n["title"])}</a></li>' for n in p.get("news", []))
    flows = p.get("top_industries") or p.get("top_sectors") or []
    flow_label = "產業 5 日法人淨流入（億元）" if p["market"] == "台股" else "類股近 20 日超額報酬（%）"
    fmax = max((abs(f.get("net_value_100m", f.get("rel_20d_pct", 0))) for f in flows), default=1) or 1
    flow_rows = "".join(
        f'<li class="{"hit" if i == (m.get("industry_rank") or m.get("sector_rank") or 0) - 1 else ""}">'
        f'<span>{e(f.get("industry") or f.get("label"))}</span>'
        f'<i style="--w:{abs(f.get("net_value_100m", f.get("rel_20d_pct", 0))) / fmax * 100:.0f}%"></i>'
        f'<b>{f.get("net_value_100m", f.get("rel_20d_pct"))}</b></li>' for i, f in enumerate(flows))
    return f"""<article class="obs">
  <header class="obs-head">
    {stock_logo(p['code'], p['name'], '上市' if p['market'] == '台股' else None, 'lg')}
    <div class="obs-title"><span class="mkt {'tw' if p['market'] == '台股' else 'us'}">{e(p['market'])}</span>
      <h3>{e(short_name(p['name']))}<small>{e(p['code'])}</small></h3><div class="obs-sub">{e(p['industry'])}・資料日 {e(p['data_date'])}</div></div>
    <div class="obs-price"><b data-count>{p['price']:,.2f}</b><small>{'新台幣' if p['market'] == '台股' else '美元'}</small></div>
  </header>
  <div class="obs-chart">{sparkline(p.get('spark'), 520, 90, 'wide')}<small>近 60 個交易日收盤</small></div>
  {f'<p class="obs-summary">{e(v["summary"])}</p>' if v.get("summary") else ''}
  <ul class="chips">{chips}</ul>
  <div class="bubbles">{personas or '<p class="empty">今天沒有產生投資人觀點</p>'}</div>
  <div class="obs-foot">
    <details class="fold"><summary>為什麼是它（選股規則與資金流）</summary>
      <p class="rule">{e(p.get('rule'))}</p><p class="flow-title">{flow_label}</p><ul class="flows">{flow_rows}</ul></details>
    {f'<details class="fold"><summary>接下來要追蹤</summary><ul class="watch">{watch}</ul></details>' if watch else ''}
    {f'<details class="fold"><summary>相關新聞（{len(p.get("news", []))}）</summary><ul class="watch">{news}</ul></details>' if news else ''}
  </div>
</article>"""


def observations(picks: dict | None, prefix: str = "") -> str:
    if not picks or not picks.get("picks"):
        return '<p class="empty">今天的觀察標的還沒產生</p>'
    cards = "".join(observation_card(p, prefix) for p in picks["picks"])
    return (f'<div class="obs-grid">{cards}</div>'
            '<p class="obs-disclaimer">依公開的資金流與產業趨勢規則每天自動篩選。四位投資人的觀點是 AI 依他們公開的投資理念模擬、依上面的數字撰寫，不是本人發言，'
            '可能有誤。這是研究素材，不是買賣建議，也不預測股價；任何投資決定請自行判斷。</p>')


# ---------- 企業 logo ----------

def logo_urls(code: str, market: str | None) -> list[str]:
    """Financial Modeling Prep 的公開 logo 圖；台股上市用 .TW、上櫃用 .TWO，不確定時兩個都試。"""
    base = "https://financialmodelingprep.com/image-stock/"
    code = (code or "").strip().upper()
    if not code:
        return []
    if "." in code:  # 已經是完整代號，例如日股 6758.T、韓股 005930.KS
        return [f"{base}{code}.png"]
    if not re.fullmatch(r"[0-9]{4,6}[A-Z]?", code):
        return [f"{base}{code}.png"]  # 美股
    if market in ("上櫃", "tpex", "TWO"):
        return [f"{base}{code}.TWO.png"]
    if market in ("上市", "twse", "TW"):
        return [f"{base}{code}.TW.png"]
    return [f"{base}{code}.TW.png", f"{base}{code}.TWO.png"]


def stock_logo(code: str, name: str = "", market: str | None = None, size: str = "") -> str:
    """logo 圖蓋在首字圖示上面；圖片 404（例如 ETF）就移除，露出底下的首字圖示。"""
    urls = logo_urls(code, market)
    hue = sum(map(ord, code or "x")) % 360
    initial = e((short_name(name) or code or "?")[:1])
    img = ""
    if urls:
        fallback = f"this.onerror=function(){{this.remove()}};this.src='{urls[1]}'" if len(urls) > 1 else "this.remove()"
        img = (f'<img src="{e(urls[0])}" alt="" loading="lazy" referrerpolicy="no-referrer" '
               f'onerror="{e(fallback)}">')
    return f'<span class="logo {size}" style="--h:{hue}"><b>{initial}</b>{img}</span>'


# ---------- 四位投資人 ----------

from investors import BY_ID, BY_NAME, INVESTORS  # noqa: E402

STANCE_CLASS.update({"偏多": "bull", "中性": "flat", "保留": "bear"})


def portrait(inv_id: str, prefix: str, cls: str = "") -> str:
    inv = BY_ID[inv_id]
    return f'<img class="portrait {cls}" src="{prefix}portraits/q/{inv_id}.svg" alt="{e(inv["name"])}（Q 版插畫）" loading="lazy">'


def source_tags(text_html: str) -> str:
    """把 [FinMind 2026Q2] 這類出處變成小標籤，「背景知識，未經本次資料驗證」變成提示標籤。"""
    text_html = re.sub(r"[（(]背景知識[^）)]*[）)]", '<span class="bk" title="AI 的背景知識，未經本次資料驗證">背景知識</span>', text_html)
    return re.sub(r"\[([^\]]{2,40})\]", r'<span class="src">\1</span>', text_html)


def bubble(inv_id: str, prefix: str, body_html: str, stance: str | None = None) -> str:
    inv = BY_ID[inv_id]
    badge = f'<span class="stance {STANCE_CLASS.get(stance, "flat")}">{e(stance)}</span>' if stance else ""
    return (f'<div class="bubble" style="--ac:{inv["accent"]}">{portrait(inv_id, prefix)}'
            f'<div class="say"><div class="who"><b>{e(inv["name"])}</b><small>{e(inv["focus"])}</small>{badge}</div>'
            f'{body_html}<div class="sim">依{e(inv["name"])}的投資框架模擬・AI 撰寫，非本人發言</div></div></div>')


def persona_bubbles_from_text(personas_text: str, prefix: str) -> str:
    """每週基本面報告的四位分析：【段永平｜...】+ 條列 → 對話泡泡。"""
    out, current = [], None
    for line in (personas_text or "").splitlines():
        line = line.strip()
        if m := re.match(r"^【(.+?)[｜|].*】$", line):
            current = {"name": m.group(1).strip(), "items": []}
            out.append(current)
        elif line and current is not None:
            current["items"].append(line[2:].strip() if line.startswith(("- ", "・")) else line)
    html_parts = []
    for sec in out:
        inv = BY_NAME.get(sec["name"])
        if not inv or not sec["items"]:
            continue
        items = "".join(f"<li>{source_tags(e(it.replace('**', '')))}</li>" for it in sec["items"])
        html_parts.append(bubble(inv["id"], prefix, f"<ul>{items}</ul>"))
    return f'<div class="bubbles">{"".join(html_parts)}</div>' if html_parts else ""


def investors_section(prefix: str, compact: bool = False) -> str:
    cards = []
    for inv in INVESTORS:
        bio = "".join(f"<li>{e(b)}</li>" for b in inv["bio"])
        phil = "".join(f"<span>{e(p)}</span>" for p in inv["philosophy"])
        cards.append(
            f'<article class="inv" style="--ac:{inv["accent"]}">{portrait(inv["id"], prefix, "big")}'
            f'<div class="inv-body"><div class="inv-name"><h3>{e(inv["name"])}</h3><small>{e(inv["en"])}</small></div>'
            f'<p class="inv-tag">「{e(inv["tagline"])}」</p><p class="inv-focus">在本站負責：{e(inv["focus"])}</p>'
            f'<div class="inv-phil">{phil}</div>'
            + ("" if compact else f'<ul class="inv-bio">{bio}</ul><p class="inv-trust"><b>為什麼值得參考</b>{e(inv["trust"])}</p>')
            + "</div></article>")
    note = ('<p class="inv-note">本站的四位投資人觀點都是 AI 依照他們公開的投資理念「模擬」撰寫，不是本人發言，也可能理解錯誤。'
            '他們的框架值得參考，但沒有人永遠是對的，巴菲特自己也在致股東信裡多次承認看錯。</p>')
    return f'<div class="invs{" compact" if compact else ""}">{"".join(cards)}</div>{note}'


# ---------- 每週研究目錄：生成式封面 ----------

def report_art(seed: str, dots: int, accent_hue: int) -> str:
    """依報告日期當種子畫的抽象封面：同心弧線＋每家公司一個圓點，每份報告都長得不一樣。"""
    import random
    rnd = random.Random(seed)
    w, h = 360, 150
    shapes = []
    cx, cy = rnd.uniform(220, 320), rnd.uniform(40, 110)
    for i in range(7):
        r = 30 + i * 22 + rnd.uniform(-6, 6)
        shapes.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.0f}" fill="none" stroke="hsl({accent_hue} 60% 70%)" '
                      f'stroke-opacity="{0.55 - i * 0.06:.2f}" stroke-width="1.2" style="--i:{i}" class="ring"/>')
    for i in range(max(dots, 3)):
        x, y = rnd.uniform(16, w - 16), rnd.uniform(16, h - 16)
        r = rnd.uniform(3, 9)
        hue = (accent_hue + rnd.choice([0, 30, 200])) % 360
        shapes.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.1f}" fill="hsl({hue} 65% 62%)" fill-opacity=".85" class="dot-a" style="--i:{i}"/>')
    pts = " ".join(f"{x},{h - 20 - rnd.uniform(0, 70) * (x / w):.0f}" for x in range(0, w + 1, 30))
    shapes.append(f'<polyline points="{pts}" fill="none" stroke="hsl({accent_hue} 70% 75%)" stroke-width="2" class="draw"/>')
    return (f'<svg class="art" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid slice" aria-hidden="true">'
            f'<rect width="{w}" height="{h}" fill="hsl({accent_hue} 45% 16%)"/>{"".join(shapes)}</svg>')
