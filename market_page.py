"""
「市場」頁：指數看板（日 K）、產業／題材熱力圖、三大法人與融資、強勢股、大戶加碼、處置／注意股、除權息行事曆。
資料來自 market.py 的 data/market/latest.json。持股提醒（holdings_alerts）只用在有密碼的 /portfolio/。
"""

import json
import re
from html import escape
from pathlib import Path

from visuals import clean_names, floor5, stock_logo


def e(x) -> str:
    return escape(str(x if x is not None else ""))


def load(path: Path) -> dict | None:
    try:
        return clean_names(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def cls(x) -> str:
    return "pos" if (x or 0) > 0 else "neg" if (x or 0) < 0 else ""


def signed(x, d=2, unit="%") -> str:
    return "—" if x is None else f"{x:+,.{d}f}{unit}"


def roc_period(p: str | None) -> str:
    return re.sub(r"(\d{3})/(\d{2})/(\d{2})", lambda m: f"{int(m[1]) + 1911}-{m[2]}-{m[3]}", p or "")


def tabs(group: str, items: list[tuple[str, str]], active: str) -> str:
    return (f'<div class="mk-tabs" data-tabs="{group}">' + "".join(
        f'<button type="button" data-tab="{k}"{" class=\"on\"" if k == active else ""}>{e(label)}</button>' for k, label in items) + "</div>")


def panel(group: str, key: str, body: str, active: bool) -> str:
    return f'<div data-panel="{group}:{key}"{"" if active else " hidden"}>{body}</div>'


# ---------- 指數看板 ----------

def spark(values: list[float], w=120, h=32) -> str:
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    pts = " ".join(f"{i / (len(values) - 1) * w:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}" for i, v in enumerate(values))
    return f'<svg class="mk-spark {cls(values[-1] - values[0])}" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><polyline points="{pts}"/></svg>'


def candles(ohlc: list[list], w=1000, h=300) -> str:
    """日 K：紅漲綠跌（台灣習慣），右側價格刻度、下方月份。"""
    if len(ohlc) < 2:
        return ""
    pad_r, pad_b = 64, 22
    lo = min(r[3] for r in ohlc)
    hi = max(r[2] for r in ohlc)
    span = hi - lo or 1
    cw = (w - pad_r) / len(ohlc)
    y = lambda v: 6 + (hi - v) / span * (h - pad_b - 12)  # noqa: E731
    out = []
    for k in range(5):
        v = lo + span * k / 4
        out.append(f'<line class="grid" x1="0" x2="{w - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text class="ax" x="{w - pad_r + 6}" y="{y(v) + 4:.1f}">{v:,.2f}</text>')
    last_month = None
    for i, (d, o, hgh, low, c) in enumerate(ohlc):
        x = i * cw + cw / 2
        tone = "up" if c >= o else "down"
        top, bot = y(max(o, c)), y(min(o, c))
        out.append(f'<g class="{tone}"><line x1="{x:.1f}" x2="{x:.1f}" y1="{y(hgh):.1f}" y2="{y(low):.1f}"/>'
                   f'<rect x="{x - cw * 0.35:.1f}" y="{top:.1f}" width="{cw * 0.7:.1f}" height="{max(bot - top, 0.8):.1f}"/></g>')
        if d[5:7] != last_month:
            last_month = d[5:7]
            out.append(f'<text class="ax" x="{x:.1f}" y="{h - 6}">{int(d[5:7])}月</text>')
    last = ohlc[-1][4]
    out.append(f'<line class="last" x1="0" x2="{w - pad_r}" y1="{y(last):.1f}" y2="{y(last):.1f}"/>')
    return f'<svg class="mk-candles" viewBox="0 0 {w} {h}" role="img" aria-label="日 K 線">{"".join(out)}</svg>'


def index_board(indices: list[dict]) -> str:
    if not indices:
        return '<p class="empty">指數資料暫時讀不到</p>'
    cards, charts = [], []
    for i, ix in enumerate(indices):
        closes = [r[4] for r in ix["ohlc"][-40:]]
        cards.append(
            f'<button type="button" class="mk-idx{" on" if i == 0 else ""}" data-tab="{i}" data-live-idx="{e(ix["ticker"])}">'
            f'<span class="mk-idx-top"><b>{e(ix["name"])}</b><small>{e(ix["region"])}</small></span>'
            f'<span class="mk-idx-val">{ix["close"]:,.2f}</span>'
            f'<span class="mk-idx-chg {cls(ix["chg"])}">{ix["chg"]:+,.2f}（{ix["chg_pct"]:+.2f}%）</span>{spark(closes)}</button>')
        o = ix["ohlc"]
        hi, lo = max(r[2] for r in o), min(r[3] for r in o)
        charts.append(panel("idx", str(i),
            f'<div class="mk-chart-head"><b>{e(ix["name"])}</b><span class="{cls(ix["chg"])}">{ix["close"]:,.2f}　{ix["chg"]:+,.2f}（{ix["chg_pct"]:+.2f}%）</span>'
            f'<small>近半年 高 {hi:,.2f}・低 {lo:,.2f}・資料日 {e(ix["date"])}</small></div>{candles(o)}', i == 0))
    return (f'<div class="mk-idx-grid" data-tabs="idx">{"".join(cards)}</div>'
            f'<div class="mk-chart">{"".join(charts)}</div>')


# ---------- 熱力圖 ----------

def squarify(values: list[float], x=0.0, y=0.0, w=100.0, h=100.0) -> list[tuple[float, float, float, float]]:
    """Squarified treemap（Bruls 等人的演算法），回傳每塊的 (x, y, w, h)，單位是百分比。"""
    total = sum(values)
    if not values or total <= 0:
        return []
    areas = [v / total * w * h for v in values]
    rects: list = []

    def worst(row, side):
        s = sum(row)
        return max(max(side * side * r / (s * s), (s * s) / (side * side * r)) for r in row)

    def layout(row, x, y, w, h):
        s = sum(row)
        if w >= h:
            col_w = s / h
            yy = y
            for r in row:
                rects.append((x, yy, col_w, r / col_w))
                yy += r / col_w
            return x + col_w, y, w - col_w, h
        row_h = s / w
        xx = x
        for r in row:
            rects.append((xx, y, r / row_h, row_h))
            xx += r / row_h
        return x, y + row_h, w, h - row_h

    row: list = []
    i = 0
    while i < len(areas):
        side = min(w, h)
        a = areas[i]
        if not row or worst(row + [a], side) <= worst(row, side):
            row.append(a)
            i += 1
        else:
            x, y, w, h = layout(row, x, y, w, h)
            row = []
    if row:
        layout(row, x, y, w, h)
    return rects


def heat_color(pct: float) -> str:
    # 紅漲綠跌；±4% 以上顏色最深
    t = max(-1.0, min(1.0, pct / 4))
    if abs(pct) < 0.05:
        return "var(--heat-flat)"
    mix = round(25 + abs(t) * 75)
    base = "var(--pos)" if t > 0 else "var(--neg)"
    return f"color-mix(in srgb, {base} {mix}%, var(--heat-flat))"


def treemap(groups: list[dict], limit: int = 24) -> str:
    groups = groups[:limit]
    rects = squarify([g["tv"] for g in groups])
    tiles = []
    for g, (x, y, w, h) in zip(groups, rects):
        tops = "、".join(f'{t["name"]} {t["pct"]:+.1f}%' for t in g["top"])
        size = "lg" if w * h > 600 else "md" if w * h > 150 else "sm" if w * h > 45 and min(w, h) > 4 else "xs"
        tiles.append(
            f'<div class="mk-tile {size}" style="left:{x:.2f}%;top:{y:.2f}%;width:{w:.2f}%;height:{h:.2f}%;background:{heat_color(g["pct"])}" '
            f'title="{e(g["name"])} {g["pct"]:+.2f}%｜上漲 {g["up"]}/{g["n"]} 檔｜{e(tops)}">'
            f'<b>{e(g["name"])}</b><span>{g["pct"]:+.2f}%</span>'
            + (f'<small>{e(tops)}</small>' if size == "lg" else "") + "</div>")
    return f'<div class="mk-tree">{"".join(tiles)}</div>'


def breadth_bar(b: dict) -> str:
    total = b["up"] + b["down"] + b["flat"] or 1
    return (f'<div class="mk-breadth"><div class="bar"><i class="up" style="width:{b["up"] / total * 100:.1f}%"></i>'
            f'<i class="flat" style="width:{b["flat"] / total * 100:.1f}%"></i><i class="down" style="width:{b["down"] / total * 100:.1f}%"></i></div>'
            f'<div class="legend"><span class="pos">上漲 {b["up"]}（漲停 {b["limit_up"]}）</span><span>平盤 {b["flat"]}</span>'
            f'<span class="neg">下跌 {b["down"]}（跌停 {b["limit_down"]}）</span></div></div>')


# ---------- 三大法人與融資 ----------

def flow_bars(hist: list[dict], key: str, w=1000, h=160) -> str:
    vals = [x.get(key) for x in hist]
    if not any(v is not None for v in vals):
        return ""
    m = max(abs(v) for v in vals if v is not None) or 1
    bw = w / len(vals)
    mid = h / 2
    bars = []
    for i, (d, v) in enumerate(zip(hist, vals)):
        if v is None:
            continue
        bh = abs(v) / m * (mid - 6)
        y = mid - bh if v > 0 else mid
        bars.append(f'<rect class="{"up" if v > 0 else "down"}" x="{i * bw + bw * 0.15:.1f}" y="{y:.1f}" width="{bw * 0.7:.1f}" height="{max(bh, 0.6):.1f}"><title>{d["date"]} {v:+,.1f} 億</title></rect>')
    return (f'<svg class="mk-bars" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><line class="grid" x1="0" x2="{w}" y1="{mid}" y2="{mid}"/>{"".join(bars)}</svg>'
            f'<div class="mk-axis"><span>{e(hist[0]["date"])}</span><span>單位：億元・最大 {m:,.0f} 億</span><span>{e(hist[-1]["date"])}</span></div>')


def margin_line(hist: list[dict], w=1000, h=160) -> str:
    pts = [(i, x["margin_yi"]) for i, x in enumerate(hist) if x.get("margin_yi")]
    if len(pts) < 2:
        return ""
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    span = hi - lo or 1
    n = len(hist) - 1 or 1
    line = " ".join(f"{i / n * w:.1f},{h - 8 - (v - lo) / span * (h - 16):.1f}" for i, v in pts)
    return (f'<svg class="mk-line" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><polyline points="{line}"/></svg>'
            f'<div class="mk-axis"><span>{e(hist[0]["date"])}</span><span>融資餘額 {lo:,.0f}～{hi:,.0f} 億</span><span>{e(hist[-1]["date"])}</span></div>')


def institutions(hist: list[dict]) -> str:
    if not hist:
        return '<p class="empty">法人資料暫時讀不到</p>'
    t = hist[-1]
    tiles = [("外資", t.get("foreign")), ("投信", t.get("trust")), ("自營商", t.get("dealer")), ("三大法人合計", t.get("total"))]
    body = '<div class="stats">' + "".join(
        f'<div class="stat"><div class="stat-label">{k}</div><div class="stat-value {cls(v)}">{signed(v, 1, "")}<span class="unit">億</span></div>'
        f'<div class="stat-foot"><span>上市・{e(t["date"])}</span></div></div>' for k, v in tiles)
    if t.get("margin_yi") is not None:
        body += (f'<div class="stat"><div class="stat-label">融資餘額</div><div class="stat-value">{t["margin_yi"]:,.0f}<span class="unit">億</span></div>'
                 f'<div class="stat-foot"><span class="{cls(t.get("margin_chg_yi"))}">單日 {signed(t.get("margin_chg_yi"), 1, " 億")}</span></div></div>')
    body += "</div>"
    groups = [("foreign", "外資"), ("trust", "投信"), ("total", "三大法人"), ("margin", "融資餘額")]
    body += tabs("flow", groups, "foreign")
    for k, _ in groups:
        body += panel("flow", k, margin_line(hist) if k == "margin" else flow_bars(hist, k), k == "foreign")
    return body


# ---------- 強勢股、大戶 ----------

def rank_list(rows: list[dict], key: str, foot) -> str:
    if not rows:
        return '<p class="empty">暫無資料</p>'
    return '<ol class="mk-rank">' + "".join(
        f'<li><span class="n">{i}</span>{stock_logo(r["code"], r["name"], r.get("market"), "sm")}'
        f'<span class="nm"><b>{e(r["name"])}</b><small>{e(r["code"])}・{e(foot(r))}</small></span>'
        f'<b class="{cls(r[key])}">{r[key]:+.2f}{"%" if key != "big_chg" else " 個百分點"}</b></li>'
        for i, r in enumerate(rows, 1)) + "</ol>"


def strong(s: dict) -> str:
    if not s:
        return '<p class="empty">暫無資料</p>'
    items = [("d", "今日"), ("w", "近 5 日"), ("m", "近 20 日")]
    return (tabs("strong", items, "w")
            + "".join(panel("strong", k, rank_list(s.get(k, [])[:10], k, lambda r: f'{r.get("industry") or ""} {r["price"]:,.2f}'), k == "w") for k, _ in items)
            + '<p class="mk-note">範圍：成交值前 250 名、持股、供應鏈與研究名單（約 300 檔）</p>')


def big_holders(b: dict) -> str:
    if not b or not b.get("prev"):
        return (f'<p class="empty">集保戶股權分散表每週五更新；已存下 {e((b or {}).get("date") or "本週")} 的資料，'
                '下週起就能比出「400 張以上大戶持股比例」的週變化。</p>')
    return (f'<p class="mk-note">{e(b["prev"])} → {e(b["date"])}，400 張以上大戶持股比例變化（股東 1,000 人以上的公司）</p>'
            + tabs("big", [("up", "大戶加碼"), ("down", "大戶減碼")], "up")
            + panel("big", "up", rank_list(b["up"][:10], "big_chg", lambda r: f'大戶 {r["big"]:.1f}%・股東 {r["holders_chg"]:+,} 人'), True)
            + panel("big", "down", rank_list(b["down"][:10], "big_chg", lambda r: f'大戶 {r["big"]:.1f}%・股東 {r["holders_chg"]:+,} 人'), False))


# ---------- 處置／注意股、除權息 ----------

LEVEL_CLASS = {"處置中": "bad", "可能處置": "warn", "注意": "note"}


def warning_cards(ws: list[dict]) -> str:
    if not ws:
        return '<p class="empty">今天沒有處置或注意股</p>'
    counts = {k: sum(w["level"] == k for w in ws) for k in LEVEL_CLASS}
    items = [(k, f"{k} {counts[k]}") for k in LEVEL_CLASS]
    out = tabs("warn", items, "處置中")
    for k in LEVEL_CLASS:
        rows = [w for w in ws if w["level"] == k and re.fullmatch(r"\d{4}", w["code"])]
        cards = "".join(
            f'<div class="mk-warn {LEVEL_CLASS[k]}"><div class="mk-warn-head">{stock_logo(w["code"], w["name"], w["market"], "sm")}'
            f'<b>{e(w["name"])}</b><small>{e(w["code"])}・{e(w["market"])}</small><span class="lv">{e(k)}</span></div>'
            + (f'<p class="period">處置期間 {e(roc_period(w["period"]))}</p>' if w.get("period") else "")
            + f'<p>{e((w["detail"] or "")[:90])}{"…" if len(w["detail"] or "") > 90 else ""}</p></div>' for w in rows[:30])
        out += panel("warn", k, f'<div class="mk-warn-grid">{cards or "<p class=empty>無</p>"}</div>', k == "處置中")
    return out + '<p class="mk-note">處置股改為人工撮合（約每 5～20 分鐘一次），部分需預收款券；「可能處置」是注意次數已接近處置標準。</p>'


def calendar(xs: list[dict], days: int = 10) -> str:
    if not xs:
        return '<p class="empty">近期沒有除權息</p>'
    dates = sorted({x["date"] for x in xs})[:days]
    out = []
    for d in dates:
        rows = [x for x in xs if x["date"] == d]
        stocks = [x for x in rows if not x["code"].startswith("00")]
        etfs = [x for x in rows if x["code"].startswith("00")]

        def row(x):
            amt = f'現金 {x["cash"]:.4g} 元' if x.get("cash") else ""
            if x.get("stock"):
                amt += f'{"・" if amt else ""}配股 {x["stock"]:.4g}'
            return (f'<li><span class="pill">{e(x["type"])}</span><b>{e(x["name"])}</b><small>{e(x["code"])}</small>'
                    f'<span class="amt">{e(amt)}</span></li>')
        body = "".join(row(x) for x in stocks)
        if etfs:
            body += f'<li class="etf"><details><summary>ETF {len(etfs)} 檔</summary><ul>{"".join(row(x) for x in etfs)}</ul></details></li>'
        out.append(f'<div class="mk-day"><h4>{int(d[5:7])}/{int(d[8:])}<small>{len(rows)} 檔</small></h4><ul>{body}</ul></div>')
    return f'<div class="mk-cal">{"".join(out)}</div><p class="mk-note">法說會沒有公開的開放資料，暫不列入。</p>'


TAB_SCRIPT = """<script>
document.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-tabs] [data-tab]");
  if (!b) return;
  const group = b.closest("[data-tabs]").dataset.tabs;
  b.parentElement.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(`[data-panel^="${group}:"]`).forEach((p) => { p.hidden = p.dataset.panel !== `${group}:${b.dataset.tab}`; });
});
</script>"""


def render(m: dict | None, hero, section, extra: dict | None = None) -> str:
    if not m:
        return hero("台股", "台股資料準備中", "下一次網站更新後就會出現。")
    date = (m.get("history") or [{}])[-1].get("date") or m["generated_at"][:10]
    body = hero("台股", "今天台股怎麼走", f"指數、產業熱力圖、法人與融資、強勢股、處置股與除權息，一頁看完・台股資料日 {e(date)}")
    body += '<main class="wrap">'
    body += section("指數看板", index_board(m.get("indices", [])), '<span class="live-dot"></span><span class="live-stamp">盤中即時更新</span>・點卡片看近半年日 K')
    heat = (tabs("heat", [("ind", "上市櫃產業"), ("theme", "供應鏈題材")], "ind")
            + panel("heat", "ind", treemap(m.get("industries", [])), True)
            + panel("heat", "theme", treemap(m.get("themes", [])), False)
            + breadth_bar(m["breadth"]))
    extra = extra or {}
    body += section("誰在推指數", contrib(extra.get("contrib")), "上市普通股・指數漲跌拆給每一檔股票")
    body += section("市場熱力圖", heat, "面積＝成交值・顏色＝成交值加權漲跌（紅漲綠跌）")
    body += section("三大法人與融資", institutions(m.get("history", [])), "上市・近 60 個交易日")
    body += section("期貨籌碼", futures(extra.get("futures")), "臺灣期貨交易所盤後資料")
    body += section("估值位置", valuation(extra.get("valuation")), "上市大盤・跟近 10 年比")
    b = extra.get("breadth")
    if b:
        body += section("市場寬度", breadth_block(b), "上市＋上櫃普通股")
        body += section("加權指數 vs 等權平均", ew_block(b), "近一年累計漲跌")
        body += section("成交金額", turnover_block(b), "近一年・線是 20 日平均")
        body += section("類股輪動圖", rrg_block(b.get("rrg") or {}), "跟加權指數比，每週一點")
    body += ('<div class="two-col">' + section("強勢股", strong(m.get("strong", {})))
             + section("大戶加碼", big_holders(m.get("big_holders", {})), "集保・每週") + "</div>")
    body += section("處置／注意股預警", warning_cards(m.get("warnings", [])), "證交所・櫃買中心公告")
    body += section("除權息行事曆", calendar(m.get("ex_dividends", [])), "未來 10 個除權息日")
    return body + "</main>" + TAB_SCRIPT


def holdings_alerts(holdings: list[dict], m: dict | None) -> str:
    """只放在 /portfolio/：持股是否在處置／注意名單、近期是否除權息（含預估配息金額）。"""
    if not m:
        return ""
    held = {h["code"]: h for h in holdings}
    items = []
    for w in m.get("warnings", []):
        if w["code"] in held:
            items.append(f'<li class="mk-alert {LEVEL_CLASS[w["level"]]}"><span class="lv">{e(w["level"])}</span><b>{e(held[w["code"]]["name"])}</b>'
                         f'<small>{e(roc_period(w.get("period")) or (w["detail"] or "")[:60])}</small></li>')
    for x in m.get("ex_dividends", []):
        h = held.get(x["code"])
        if h:
            est = f'・預估現金 {x["cash"] * (h.get("shares") or 0):,.0f} 元' if x.get("cash") and h.get("shares") else ""
            items.append(f'<li class="mk-alert div"><span class="lv">{e(x["type"])}</span><b>{e(h["name"])}</b>'
                         f'<small>{e(x["date"])}・每股 {x.get("cash") or 0:.4g} 元{e(est)}</small></li>')
    if not items:
        return '<p class="empty">持股目前沒有處置、注意，近期也沒有除權息。</p>'
    return f'<ul class="mk-alerts">{"".join(items)}</ul>'


# ---------- 首頁「本日市場速報」 ----------
# 全部由 latest.json 的真實數字依固定規則組句，不用 LLM，不寫因果推論（不說「因為…所以跌」）。

WEEK = "一二三四五六日"


def _md(iso: str) -> str:
    from datetime import date
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}（{WEEK[d.weekday()]}）"


def _yi(x: float) -> str:
    return f"{'買超' if x >= 0 else '賣超'} {abs(x):,.1f} 億"


def _streak(hist: list[dict], key: str) -> int:
    """最近連續同方向的天數（正＝連買、負＝連賣）。"""
    n, sign = 0, None
    for h in reversed(hist):
        v = h.get(key)
        if v is None or v == 0:
            break
        s = v > 0
        if sign is None:
            sign = s
        if s != sign:
            break
        n += 1
    return n if sign else -n


def brief(m: dict | None, extras: list[tuple[str, str, str]] = (), today: str = "") -> str:
    """extras：(標籤, 內文 HTML, 連結)，由 build.py 補上研究候選新進、早報頭條等。"""
    if not m or not m.get("indices"):
        return '<p class="empty">市場資料暫時讀不到</p>'
    ix = {i["ticker"]: i for i in m["indices"]}
    tw = ix.get("^TWII") or m["indices"][0]
    b = m.get("breadth") or {}
    hist = m.get("history") or []
    h = hist[-1] if hist and hist[-1]["date"] == tw["date"] else None
    stale = today and tw["date"] != today

    # 一句話總結
    mood = ("漲多跌少" if b.get("up", 0) > b.get("down", 0) * 1.2 else
            "跌多漲少" if b.get("down", 0) > b.get("up", 0) * 1.2 else "漲跌互見") if b else ""
    lead = (f'台股加權收 <b>{tw["close"]:,.0f}</b>，{"上漲" if tw["chg"] >= 0 else "下跌"} '
            f'<b class="{cls(tw["chg"])}">{abs(tw["chg"]):,.0f} 點（{tw["chg_pct"]:+.2f}%）</b>')
    if b:
        lead += f'；{mood}（{b["up"]} 漲／{b["down"]} 跌）'
    if h:
        lead += f'，三大法人合計<b class="{cls(h["total"])}">{_yi(h["total"])}</b>'
        if h.get("margin_chg_yi") is not None:
            lead += f'，融資{"增加" if h["margin_chg_yi"] >= 0 else "減少"} {abs(h["margin_chg_yi"]):,.1f} 億'
    lead += "。"

    # 數字磚：加權（盤中即時更新）、漲跌家數、外資、融資
    tiles = [
        f'<div class="br-tile br-idx" data-live-idx="^TWII"><small>台股加權</small>'
        f'<span class="mk-idx-val">{tw["close"]:,.2f}</span>'
        f'<span class="mk-idx-chg {cls(tw["chg"])}">{tw["chg"]:+,.2f}（{tw["chg_pct"]:+.2f}%）</span></div>']
    if b:
        tot = (b["up"] + b["down"] + b["flat"]) or 1
        tiles.append(f'<div class="br-tile"><small>漲跌家數</small><span><b class="pos">{b["up"]}</b> / <b class="neg">{b["down"]}</b></span>'
                     f'<div class="br-bar"><i class="up" style="width:{b["up"] / tot * 100:.1f}%"></i><i class="flat" style="width:{b["flat"] / tot * 100:.1f}%"></i>'
                     f'<i class="down" style="width:{b["down"] / tot * 100:.1f}%"></i></div><small>漲停 {b["limit_up"]}・跌停 {b["limit_down"]}</small></div>')
    if h:
        fs = _streak(hist, "foreign")
        streak = f'連 {abs(fs)} 日{"買" if fs > 0 else "賣"}' if abs(fs) >= 2 else ""
        tiles.append(f'<div class="br-tile"><small>外資</small><span class="{cls(h["foreign"])}">{_yi(h["foreign"])}</span>'
                     f'<small>投信 {_yi(h["trust"])}・自營 {_yi(h["dealer"])}{"・" + streak if streak else ""}</small></div>')
        if h.get("margin_chg_yi") is not None:
            tiles.append(f'<div class="br-tile"><small>融資餘額</small><span>{h["margin_yi"]:,.0f} 億</span>'
                         f'<small class="{cls(h["margin_chg_yi"])}">{"增" if h["margin_chg_yi"] >= 0 else "減"} {abs(h["margin_chg_yi"]):,.1f} 億</small></div>')

    # 重點條列
    pts = []
    themes = sorted(m.get("themes") or [], key=lambda t: -t["pct"])
    if themes:
        hot = "、".join(f'{e(t["name"])} <b class="{cls(t["pct"])}">{t["pct"]:+.1f}%</b>' for t in themes[:3])
        cold = "、".join(f'{e(t["name"])} <b class="{cls(t["pct"])}">{t["pct"]:+.1f}%</b>' for t in themes[-2:][::-1])
        pts.append(("族群", f"最強：{hot}；最弱：{cold}", "market/index.html"))
    sd = (m.get("strong") or {}).get("d") or []
    if sd:
        pts.append(("強勢股", "、".join(f'{e(s["name"])} <b class="{cls(s["d"])}">{s["d"]:+.1f}%</b>' for s in sd[:4]), "market/index.html"))
    us = [ix[t] for t in ("^GSPC", "^IXIC", "^SOX", "TSM") if t in ix]
    if us and us[0]["date"] >= tw["date"]:
        pts.append(("美股", f'{_md(us[0]["date"])}：' + "、".join(
            f'{e(u["name"])} <b class="{cls(u["chg_pct"])}">{u["chg_pct"]:+.2f}%</b>' for u in us), "us/index.html"))
    risk = []
    if "^VIX" in ix:
        risk.append(f'VIX {ix["^VIX"]["close"]:.1f}')
    if "TWD=X" in ix:
        risk.append(f'美元兌台幣 {ix["TWD=X"]["close"]:.2f}')
    ws = m.get("warnings") or []
    n_dis = sum(1 for w in ws if w["level"] == "處置中")
    n_may = sum(1 for w in ws if w["level"] == "可能處置")
    if ws:
        risk.append(f"處置中 {n_dis} 檔、可能處置 {n_may} 檔")
    if risk:
        pts.append(("風險", "・".join(risk), "market/index.html"))
    upcoming = sorted({x["date"] for x in m.get("ex_dividends") or [] if x["date"] > tw["date"]})
    if upcoming:
        d0 = upcoming[0]
        xs = [x for x in m["ex_dividends"] if x["date"] == d0]
        names = "、".join(e(x["name"]) for x in xs[:4]) + (f" 等 {len(xs)} 檔" if len(xs) > 4 else "")
        pts.append(("除權息", f"{_md(d0)}：{names}", "market/index.html"))
    pts += list(extras)

    items = "".join(f'<li><span class="br-tag">{e(t)}</span><span class="br-txt">{txt}</span>'
                    f'{f"<a href={chr(34)}{href}{chr(34)}>→</a>" if href else ""}</li>' for t, txt, href in pts)
    note = (f'{"最近交易日" if stale else "今日"}收盤 {_md(tw["date"])}・盤中加權指數每分鐘更新'
            f'・資料更新於 {e(floor5(m.get("generated_at")))}')
    return (f'<div class="brief"><p class="br-lead">{lead}</p><div class="br-tiles">{"".join(tiles)}</div>'
            f'<ul class="br-pts">{items}</ul><p class="br-note">{note}</p></div>')


# ---------- 進階：誰在推指數、估值位置、期貨籌碼（data/market/extra.json） ----------

PARTS = [("tsmc", "台積電", "p-tsmc"), ("top10", "其他前十大權值股", "p-top"), ("rest", "其餘上市股票", "p-rest")]


def _share(v: float, total: float) -> str:
    return "–" if abs(total) < 30 else f"{v / total * 100:.0f}%"


def contrib_panel(row: dict, label: str, push=None, drag=None) -> str:
    total = row["index"]
    scale = max(abs(row[k]) for k, _, _ in PARTS) or 1
    bars = "".join(
        f'<li><span class="nm">{n}</span><span class="cb-track"><i class="{c} {"up" if row[k] >= 0 else "down"}" '
        f'style="width:{abs(row[k]) / scale * 100:.1f}%"></i></span><b class="{cls(row[k])}">{row[k]:+,.1f} 點</b>'
        f'<small>{_share(row[k], total)}</small></li>' for k, n, c in PARTS)
    head = f'<p class="cb-head">加權指數 <b class="{cls(total)}">{total:+,.1f} 點</b>（{e(label)}）</p>'
    lists = ""
    if push or drag:
        li = lambda xs: "".join(f'<li>{stock_logo(x["code"], x["name"], "上市", "sm")}<span>{e(x["name"])}</span>'
                                f'<b class="{cls(x["pts"])}">{x["pts"]:+.1f} 點</b><small class="{cls(x["pct"])}">{x["pct"]:+.2f}%</small></li>' for x in xs)
        lists = (f'<div class="cb-lists"><div><h4>推升最多</h4><ol>{li(push) or "<li class=empty>—</li>"}</ol></div>'
                 f'<div><h4>拖累最多</h4><ol>{li(drag) or "<li class=empty>—</li>"}</ol></div></div>')
    return head + f'<ol class="cb-bars">{bars}</ol>' + lists


def contrib_chart(hist: list[dict], w=1000, h=200) -> str:
    if len(hist) < 2:
        return ""
    m = max(max(sum(max(d[k], 0) for k, _, _ in PARTS), -sum(min(d[k], 0) for k, _, _ in PARTS), abs(d["index"])) for d in hist) or 1
    bw, mid = w / len(hist), h / 2
    out = []
    for i, d in enumerate(hist):
        up = dn = 0.0
        for k, _, c in PARTS:
            v = d[k]
            bh = abs(v) / m * (mid - 6)
            if v >= 0:
                y = mid - up - bh
                up += bh
            else:
                y = mid + dn
                dn += bh
            out.append(f'<rect class="{c}" x="{i * bw + bw * 0.15:.1f}" y="{y:.1f}" width="{bw * 0.7:.1f}" height="{max(bh, 0.4):.1f}">'
                       f'<title>{d["date"]} 台積電 {d["tsmc"]:+.0f}・前十大 {d["top10"]:+.0f}・其餘 {d["rest"]:+.0f}（指數 {d["index"]:+.0f}）</title></rect>')
        out.append(f'<circle class="cb-dot" cx="{i * bw + bw / 2:.1f}" cy="{mid - d["index"] / m * (mid - 6):.1f}" r="2.6"/>')
    legend = "".join(f'<span><i class="{c}"></i>{n}</span>' for _, n, c in PARTS) + '<span><i class="cb-dot"></i>指數實際漲跌</span>'
    return (f'<svg class="mk-bars cb-chart" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><line class="grid" x1="0" x2="{w}" y1="{mid}" y2="{mid}"/>{"".join(out)}</svg>'
            f'<div class="mk-axis"><span>{e(hist[0]["date"])}</span><span>單位：指數點數・最大 {m:,.0f} 點</span><span>{e(hist[-1]["date"])}</span></div>'
            f'<div class="cb-legend">{legend}</div>')


def contrib(c: dict | None) -> str:
    if not c:
        return '<p class="empty">資料準備中</p>'
    items = [("d", "今日")] + [(k, k) for k in (c.get("periods") or {})]
    panels = panel("cb", "d", contrib_panel(c, f'{c["date"]}，與前一交易日收盤相比', c.get("push"), c.get("drag")), True)
    for k, row in (c.get("periods") or {}).items():
        panels += panel("cb", k, contrib_panel(row, f"近 {k}累計"), False)
    note = (f'<p class="mk-note">貢獻點數＝個股市值變化 ÷ 指數除數（前一日上市總市值 ÷ 前一日指數）。台積電目前約占上市市值 {c.get("tsmc_weight") or "—"}%。'
            "股數用目前已發行股數，歷史日期是近似值；「其餘上市股票」與指數實際漲跌的小差異來自除數調整與四捨五入。</p>")
    return (tabs("cb", items, "d") + panels
            + '<h4 class="cb-sub">近 60 個交易日，每天的漲跌從哪裡來</h4>' + contrib_chart(c.get("history") or []) + note)


def pct_bar(p: int | None, reverse: bool = False, span: str = "近 10 年") -> str:
    if p is None:
        return ""
    hot = p >= 80 if not reverse else p <= 20
    cold = p <= 20 if not reverse else p >= 80
    return (f'<div class="pb"><span class="pb-track"><i style="left:{p}%"></i></span>'
            f'<small class="{"hot" if hot else "cold" if cold else ""}">{span}第 {p} 百分位</small></div>')


def pe_chart(series: list[dict], median: float | None, w=1000, h=170) -> str:
    pts = [(s["date"], s["pe"]) for s in series if s.get("pe")]
    if len(pts) < 3:
        return ""
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    span = hi - lo or 1
    y = lambda v: h - 10 - (v - lo) / span * (h - 20)
    line = " ".join(f"{i / (len(pts) - 1) * w:.1f},{y(v):.1f}" for i, (_, v) in enumerate(pts))
    med = f'<line class="pe-med" x1="0" x2="{w}" y1="{y(median):.1f}" y2="{y(median):.1f}"/>' if median else ""
    return (f'<svg class="mk-bars pe-chart" viewBox="0 0 {w} {h}" preserveAspectRatio="none">{med}<polyline points="{line}"/></svg>'
            f'<div class="mk-axis"><span>{e(pts[0][0][:7])}</span><span>本益比 {lo:.1f}～{hi:.1f} 倍・虛線＝中位數 {median or "—"} 倍</span><span>{e(pts[-1][0])}</span></div>')


def valuation(v: dict | None) -> str:
    if not v:
        return '<p class="empty">資料準備中</p>'
    p, md = v.get("pct") or {}, v.get("median") or {}
    tiles = (f'<div class="vt"><small>上市大盤本益比</small><b>{v["pe"]} 倍</b>{pct_bar(p.get("pe"))}<span>10 年中位數 {md.get("pe") or "—"} 倍</span></div>'
             f'<div class="vt"><small>股價淨值比</small><b>{v["pb"]} 倍</b>{pct_bar(p.get("pb"))}<span>10 年中位數 {md.get("pb") or "—"} 倍</span></div>'
             f'<div class="vt"><small>現金殖利率</small><b>{v["yield"]}%</b>{pct_bar(p.get("yield"), reverse=True)}<span>10 年中位數 {md.get("yield") or "—"}%</span></div>'
             f'<div class="vt"><small>上市總市值</small><b>{v["cap_trillion"]} 兆</b><span>資料日 {e(v["date"])}</span></div>')
    note = (f'<p class="mk-note">「近 10 年第 X 百分位」＝近 10 年有 X% 的時候比今天低或一樣：本益比、淨值比越高代表越貴；殖利率相反，越低越貴。'
            f'市值加權，本益比只算有獲利的公司。歷史從 {e(v.get("since", "")[:7])} 起每月取一點（共 {v.get("n_points")} 點），'
            f'股數用目前的已發行股數，是近似值。資料：證交所每日本益比、殖利率及股價淨值比。</p>')
    return f'<div class="vt-grid">{tiles}</div>' + pe_chart(v.get("series") or [], md.get("pe")) + note


def futures(f: dict | None) -> str:
    if not f:
        return '<p class="empty">資料準備中</p>'
    prev = f.get("prev") or {}
    d = lambda k, unit="": (f'前一日 {prev[k]:+,}{unit}' if isinstance(prev.get(k), int) else f'前一日 {prev[k]:+.2f}{unit}') if prev.get(k) is not None else ""
    rr = f.get("retail_ratio")
    tiles = (f'<div class="vt"><small>散戶小台＋微台多空比</small><b class="{cls(rr)}">{rr:+.2f}%</b>'
             f'<span>{d("retail_ratio", "%")}{"・小台 " + format(f["retail_mtx"], "+.2f") + "%" if f.get("retail_mtx") is not None else ""}'
             f'{"・微台 " + format(f["retail_tmf"], "+.2f") + "%" if f.get("retail_tmf") is not None else ""}</span>'
             + (f'<span>累積 {f["n_days"]} 天中第 {f["retail_pct"]} 百分位</span>' if f.get("retail_pct") is not None and f.get("n_days", 0) >= 20 else "")
             + '</div>'
             f'<div class="vt"><small>外資台指期淨未平倉</small><b class="{cls(f["foreign_tx"])}">{f["foreign_tx"]:+,} 口</b><span>{d("foreign_tx", " 口")}</span></div>'
             f'<div class="vt"><small>Put/Call 比（未平倉）</small><b>{f["pc_oi"] or "—"}%</b><span>{d("pc_oi", "%")}</span></div>')
    pcs = f.get("pc_series") or []
    chart = ""
    if len(pcs) >= 3:
        lo, hi = min(x["v"] for x in pcs), max(x["v"] for x in pcs)
        span = hi - lo or 1
        line = " ".join(f'{i / (len(pcs) - 1) * 1000:.1f},{150 - (x["v"] - lo) / span * 130:.1f}' for i, x in enumerate(pcs))
        chart = (f'<h4 class="cb-sub">Put/Call 比（未平倉）近 {len(pcs)} 個交易日</h4>'
                 f'<svg class="mk-bars pe-chart" viewBox="0 0 1000 160" preserveAspectRatio="none"><polyline points="{line}"/></svg>'
                 f'<div class="mk-axis"><span>{e(pcs[0]["date"])}</span><span>{lo:.0f}%～{hi:.0f}%</span><span>{e(pcs[-1]["date"])}</span></div>')
    note = ('<p class="mk-note">散戶多空比＝散戶手上小台、微台的多單減空單，占全市場未平倉的比例：正的代表散戶整體偏多。'
            '期交所沒有直接公布散戶部位，這裡用全市場未平倉扣掉外資、投信、自營商算出來；微台 5 口算 1 口小台。'
            '外資手上有大量台股，台指期空單多半是避險，所以常常是淨空，單看看不出外資多空。'
            f'Put/Call 比＝賣權未平倉 ÷ 買權未平倉。資料：臺灣期貨交易所，資料日 {e(f["date"])}；多空比的歷史從現在開始每天累積。</p>')
    return f'<div class="vt-grid">{tiles}</div>' + chart + note


# ---------- 市場寬度、加權 vs 等權、成交金額、類股輪動（data/market/breadth.json） ----------

def _lines(series: list[tuple[list, str]], dates: list[str], unit: str = "", w=1000, h=180, right=None) -> str:
    """多條折線；right＝(values, class, label) 畫在右軸（自己的刻度）。"""
    allv = [v for vals, _ in series for v in vals if v is not None]
    if not allv or len(dates) < 2:
        return ""
    lo, hi = min(allv), max(allv)
    span = hi - lo or 1
    n = len(dates)
    def path(vals, a, b):
        sp = b - a or 1
        return " ".join(f"{i / (n - 1) * w:.1f},{h - 8 - (v - a) / sp * (h - 16):.1f}" for i, v in enumerate(vals) if v is not None)
    out = [f'<polyline class="ln {c}" points="{path(vals, lo, hi)}"/>' for vals, c in series]
    if right:
        rv = [v for v in right[0] if v is not None]
        out.insert(0, f'<polyline class="ln {right[1]}" points="{path(right[0], min(rv), max(rv))}"/>')
    zero = f'<line class="grid" x1="0" x2="{w}" y1="{h - 8 - (0 - lo) / span * (h - 16):.1f}" y2="{h - 8 - (0 - lo) / span * (h - 16):.1f}"/>' if lo < 0 < hi else ""
    return (f'<svg class="mk-bars lines" viewBox="0 0 {w} {h}" preserveAspectRatio="none">{zero}{"".join(out)}</svg>'
            f'<div class="mk-axis"><span>{e(dates[0])}</span><span>{lo:,.0f}{unit} ～ {hi:,.0f}{unit}</span><span>{e(dates[-1])}</span></div>')


def _legend(items: list[tuple[str, str]]) -> str:
    return '<div class="cb-legend">' + "".join(f'<span><i class="lg {c}"></i>{e(n)}</span>' for n, c in items) + "</div>"


def breadth_block(b: dict) -> str:
    t = b["today"]
    p = t.get("above60_pct")
    tiles = (f'<div class="vt"><small>上漲 / 下跌家數</small><b><span class="pos">{t["up"]:,}</span> / <span class="neg">{t["down"]:,}</span></b><span>資料日 {e(b["date"])}・共 {b["n_stocks"]:,} 檔普通股</span></div>'
             f'<div class="vt"><small>52 週新高 / 新低</small><b><span class="pos">{t["new_hi"]}</span> / <span class="neg">{t["new_lo"]}</span></b><span>收盤創一年新高、新低的家數</span></div>'
             f'<div class="vt"><small>站上季線的股票</small><b>{t["above60"]}%</b>{pct_bar(p, span=f"近 {round((t.get('above60_days') or 0) / 250, 1):g} 年")}<span>月線 {t["above20"]}%・年線 {t["above240"] if t.get("above240") is not None else "—"}%</span></div>')
    ad = b.get("ad_line") or []
    tx = {x["date"]: x["v"] for x in b.get("taiex_1y") or []}
    dates = [x["date"] for x in ad]
    adc = _lines([([x["v"] for x in ad], "l-ad")], dates, right=([tx.get(d) for d in dates], "l-tx"))
    hl = b.get("new_hl") or []
    m = max([max(x["hi"], x["lo"]) for x in hl] or [1]) or 1
    bw = 1000 / max(len(hl), 1)
    bars = "".join(f'<rect class="up" x="{i * bw:.1f}" y="{80 - x["hi"] / m * 74:.1f}" width="{bw * 0.8:.1f}" height="{x["hi"] / m * 74:.1f}"><title>{x["date"]} 新高 {x["hi"]}</title></rect>'
                   f'<rect class="down" x="{i * bw:.1f}" y="80" width="{bw * 0.8:.1f}" height="{x["lo"] / m * 74:.1f}"><title>{x["date"]} 新低 {x["lo"]}</title></rect>' for i, x in enumerate(hl))
    hlc = (f'<svg class="mk-bars" viewBox="0 0 1000 160" preserveAspectRatio="none"><line class="grid" x1="0" x2="1000" y1="80" y2="80"/>{bars}</svg>'
           f'<div class="mk-axis"><span>{e(hl[0]["date"]) if hl else ""}</span><span>上＝新高家數、下＝新低家數・最多 {m} 檔</span><span>{e(hl[-1]["date"]) if hl else ""}</span></div>') if hl else ""
    ab = b.get("above") or []
    abc = _lines([([x["m20"] for x in ab], "l-m20"), ([x["m60"] for x in ab], "l-m60"), ([x.get("m240") for x in ab], "l-m240")],
                 [x["date"] for x in ab], "%")
    return (f'<div class="vt-grid">{tiles}</div>'
            + '<h4 class="cb-sub">騰落線 vs 加權指數（近一年）</h4>' + adc + _legend([("騰落線（每天上漲−下跌家數，累加）", "l-ad"), ("加權指數（右軸）", "l-tx")])
            + '<p class="mk-note">指數創高而騰落線沒有跟上，代表上漲集中在少數股票。</p>'
            + '<h4 class="cb-sub">52 週新高 / 新低家數（近一年）</h4>' + hlc
            + '<h4 class="cb-sub">站上均線的股票比例（近兩年）</h4>' + abc
            + _legend([("20 日線", "l-m20"), ("60 日線（季線）", "l-m60"), ("240 日線（年線）", "l-m240")])
            + f'<p class="mk-note">線越高代表越多股票處在上升趨勢（普漲）；指數上漲但這條線往下，代表只有少數股票在撐。'
            f'季線比例的百分位是跟近 {round((t.get("above60_days") or 0) / 250, 1)} 年比較。價格用還原權值股價，除權息不會被誤判成跌破均線。'
            f'資料：Yahoo Finance 全部上市櫃普通股日線。</p>')


def ew_block(b: dict) -> str:
    xs = b.get("ew_vs_cap") or []
    t = b["today"]
    chart = _lines([([x["cap"] for x in xs], "l-tx"), ([x["ew"] for x in xs], "l-ew")], [x["date"] for x in xs], "%")
    return (f'<p class="cb-head">近一年：加權指數 <b class="{cls(t["taiex_1y"])}">{t["taiex_1y"]:+.1f}%</b>，'
            f'全部上市股票等權平均 <b class="{cls(t["ew_1y"])}">{t["ew_1y"]:+.1f}%</b></p>' + chart
            + _legend([("加權指數（市值加權，台積電約占四成）", "l-tx"), ("等權平均（每檔一樣重）", "l-ew")])
            + '<p class="mk-note">兩條線拉開，代表大型權值股和一般股票走得不一樣：加權遠高於等權＝漲幅集中在大公司。</p>')


def turnover_block(b: dict) -> str:
    xs = b.get("turnover") or []
    if not xs:
        return ""
    t = b["today"]
    m = max(x["v"] for x in xs) or 1
    bw = 1000 / len(xs)
    bars = "".join(f'<rect class="tv" x="{i * bw:.1f}" y="{160 - x["v"] / m * 150:.1f}" width="{bw * 0.75:.1f}" height="{x["v"] / m * 150:.1f}"><title>{x["date"]} {x["v"]:,} 億</title></rect>' for i, x in enumerate(xs))
    ma = " ".join(f'{i * bw + bw / 2:.1f},{160 - x["ma20"] / m * 150:.1f}' for i, x in enumerate(xs) if x.get("ma20"))
    ratio = t["turnover"] / t["turnover_ma20"] if t.get("turnover_ma20") else None
    return (f'<p class="cb-head">{e(b["date"])} 成交約 <b>{t["turnover"]:,} 億</b>，是近 20 日平均（{t["turnover_ma20"]:,} 億）的 '
            f'<b class="{"pos" if (ratio or 1) > 1.2 else "neg" if (ratio or 1) < 0.8 else ""}">{ratio:.2f} 倍</b></p>'
            f'<svg class="mk-bars" viewBox="0 0 1000 162" preserveAspectRatio="none">{bars}<polyline class="ln l-ma" points="{ma}"/></svg>'
            f'<div class="mk-axis"><span>{e(xs[0]["date"])}</span><span>最高 {m:,} 億</span><span>{e(xs[-1]["date"])}</span></div>'
            + _legend([("每日成交金額（上市＋上櫃普通股）", "l-tvb"), ("20 日平均", "l-ma")])
            + '<p class="mk-note">柱子明顯高過橘線，代表當天交易比平常熱烈，常出現在大漲、大跌或重大消息的日子。成交金額＝每檔收盤價 × 成交股數加總，是約略值。</p>')


QUAD = {"領先": "q-lead", "轉弱": "q-weak", "落後": "q-lag", "改善": "q-imp"}


def rrg_chart(groups: list[dict], key: str, w=640, h=480) -> str:
    pts = [p for g in groups for p in g["trail"]]
    if not pts:
        return '<p class="empty">資料不足</p>'
    # 刻度依大多數族群決定（第 85 百分位），少數跑很遠的點貼在邊框上，不讓一條線把其他全部擠在中間
    q85 = lambda vals: sorted(vals)[int(len(vals) * 0.85)] if vals else 2
    rx = max(q85([abs(p["x"] - 100) for p in pts]), 1.5) * 1.25
    ry = max(q85([abs(p["y"] - 100) for p in pts]), 1.5) * 1.25
    clamp = lambda v, lim: max(-lim, min(lim, v))
    X = lambda v: w / 2 + clamp((v - 100) / rx, 1) * (w / 2 - 14)
    Y = lambda v: h / 2 - clamp((v - 100) / ry, 1) * (h / 2 - 14)
    bg = (f'<rect class="q q-lead" x="{w / 2}" y="0" width="{w / 2}" height="{h / 2}"/><rect class="q q-weak" x="{w / 2}" y="{h / 2}" width="{w / 2}" height="{h / 2}"/>'
          f'<rect class="q q-lag" x="0" y="{h / 2}" width="{w / 2}" height="{h / 2}"/><rect class="q q-imp" x="0" y="0" width="{w / 2}" height="{h / 2}"/>'
          f'<line class="axis" x1="{w / 2}" x2="{w / 2}" y1="0" y2="{h}"/><line class="axis" x1="0" x2="{w}" y1="{h / 2}" y2="{h / 2}"/>'
          f'<text class="ql" x="{w - 8}" y="18" text-anchor="end">領先</text><text class="ql" x="{w - 8}" y="{h - 8}" text-anchor="end">轉弱</text>'
          f'<text class="ql" x="8" y="{h - 8}">落後</text><text class="ql" x="8" y="18">改善</text>')
    lines = []
    for i, g in enumerate(groups):
        tr = g["trail"][-6:]
        hue = (i * 47) % 360
        path = " ".join(f'{X(p["x"]):.1f},{Y(p["y"]):.1f}' for p in tr)
        dots = "".join(f'<circle cx="{X(p["x"]):.1f}" cy="{Y(p["y"]):.1f}" r="2"/>' for p in tr[:-1])
        last = tr[-1]
        lines.append(f'<g class="rg" data-g="{e(g["name"])}" style="--c:hsl({hue} 80% 62%)"><title>{e(g["name"])}：相對強弱 {last["x"]}、動能 {last["y"]}（{g["quadrant"]}）</title>'
                     f'<polyline points="{path}"/>{dots}<circle class="head" cx="{X(last["x"]):.1f}" cy="{Y(last["y"]):.1f}" r="5"/>'
                     + (f'<text x="{X(last["x"]) - 7:.1f}" y="{Y(last["y"]) + 4:.1f}" text-anchor="end">{e(g["name"])}</text></g>'
                        if X(last["x"]) > w - 130 else f'<text x="{X(last["x"]) + 7:.1f}" y="{Y(last["y"]) + 4:.1f}">{e(g["name"])}</text></g>'))
    return f'<svg class="rrg" viewBox="0 0 {w} {h}" data-rrg="{key}">{bg}{"".join(lines)}</svg>'


def rrg_lists(groups: list[dict]) -> str:
    rows = "".join(f'<li><b class="{QUAD[q]}">{q}</b><span>{e("、".join(g["name"] for g in groups if g["quadrant"] == q) or "—")}</span></li>'
                   for q in ("領先", "轉弱", "落後", "改善"))
    moved = [g for g in groups if g.get("prev_quadrant") and g["prev_quadrant"] != g["quadrant"]]
    mv = "".join(f'<li>{e(g["name"])}：{g["prev_quadrant"]} → <b class="{QUAD[g["quadrant"]]}">{g["quadrant"]}</b></li>' for g in moved)
    return (f'<ul class="rrg-now">{rows}</ul>'
            + (f'<h4 class="cb-sub">這一週換了區的</h4><ul class="rrg-moved">{mv}</ul>' if mv else ""))


def rrg_block(r: dict) -> str:
    peer, ind = r.get("peer") or [], r.get("industry") or []
    # 產業別太多會擠在一起：圖上只畫離中心最遠（最有方向性）的 12 個，下面清單列全部
    far = sorted(ind, key=lambda g: -abs(g["trail"][-1]["x"] - 100) - abs(g["trail"][-1]["y"] - 100))[:12]
    items = [("peer", "AI 供應鏈族群"), ("ind", "交易所產業別")]
    return (tabs("rrg", items, "peer")
            + panel("rrg", "peer", f'<div class="rrg-wrap">{rrg_chart(peer, "peer")}<div>{rrg_lists(peer)}</div></div>', True)
            + panel("rrg", "ind", f'<div class="rrg-wrap">{rrg_chart(far, "ind")}<div>{rrg_lists(ind)}</div></div>', False)
            + '<p class="mk-note">一條線＝一個族群最近 6 週的路徑，每週一點，有名字的大圓點是今天。越右邊＝最近比大盤強；越上面＝跟大盤比越來越強。'
            '常見的走法是順時針：改善 → 領先 → 轉弱 → 落後。相對強弱＝族群等權指數 ÷ 加權指數，再跟自己近 50 個交易日平均比（100 為分界）；'
            '動能＝相對強弱跟 10 個交易日前比（100 為分界）。只描述位置與方向，不代表買賣時機。滑鼠移到線上看數字。</p>')
