"""
「美股」頁：指數與利率、類股強弱、市值熱力圖、重點個股（SEC 官方財報）、財報行事曆、近期 SEC 申報。
資料來自 us.py 的 data/us/latest.json；報價盤中由 site.js 透過 /api/live 每分鐘更新。
"""

from datetime import date
from html import escape

from market_page import TAB_SCRIPT, cls, heat_color, panel, spark, squarify, tabs
from visuals import floor5, stock_logo

WEEK = "一二三四五六日"


def e(x) -> str:
    return escape(str(x if x is not None else ""))


def md(iso: str | None) -> str:
    if not iso:
        return "—"
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}（{WEEK[d.weekday()]}）"


def sp(x, d=1) -> str:
    return "—" if x is None else f'<span class="{cls(x)}">{x:+.{d}f}%</span>'


def money(v) -> str:
    if v is None:
        return "—"
    a = abs(v)  # 1 億＝1e8，1 兆＝1e12
    s = f"{a / 1e12:.2f} 兆" if a >= 1e12 else f"{a / 1e8:,.0f} 億"
    return ("−" if v < 0 else "") + s + " 美元"


# ---------- 指數與利率 ----------

def index_cards(ixs: list[dict]) -> str:
    out = []
    for ix in ixs:
        rate = ix["ticker"] == "^TNX"
        val = f'{ix["price"]:.2f}%' if rate else f'{ix["price"]:,.2f}'
        chg = (f'{ix["chg"] * 100:+.0f} 個基點' if rate else f'{ix["chg"]:+,.2f}（{ix["d1"]:+.2f}%）')
        live = "" if rate else f' data-live-idx="{e(ix["ticker"])}"'
        out.append(f'<div class="mk-idx us-idx"{live}><span class="mk-idx-top"><b>{e(ix["name"])}</b></span>'
                   f'<span class="mk-idx-val">{val}</span><span class="mk-idx-chg {cls(ix["chg"])}">{chg}</span>{spark(ix["spark"])}</div>')
    return f'<div class="mk-idx-grid">{"".join(out)}</div>'


# ---------- 類股強弱 ----------

def sector_bars(secs: list[dict]) -> str:
    items = [("d1", "今日"), ("d5", "近 5 日"), ("m1", "近 1 個月"), ("ytd", "今年以來")]
    panels = []
    for k, _ in items:
        rows = sorted((s for s in secs if s.get(k) is not None), key=lambda s: -s[k])
        top = max((abs(s[k]) for s in rows), default=1) or 1
        bars = "".join(
            f'<li><span class="nm"><b>{e(s["name"])}</b><small>{e(s["ticker"])}</small></span>'
            f'<span class="bar"><i class="{cls(s[k])}" style="width:{abs(s[k]) / top * 100:.1f}%"></i></span>'
            f'<b class="{cls(s[k])}">{s[k]:+.2f}%</b></li>' for s in rows)
        panels.append(panel("sec", k, f'<ol class="us-bars">{bars}</ol>', k == "d1"))
    return tabs("sec", items, "d1") + "".join(panels) + '<p class="mk-note">以 SPDR 類股 ETF（半導體用 SMH）代表各類股表現</p>'


# ---------- 熱力圖 ----------

def heatmap(stocks: list[dict]) -> str:
    xs = sorted((s for s in stocks if s.get("mcap") and s.get("d1") is not None), key=lambda s: -s["mcap"])
    if not xs:
        return '<p class="empty">暫無資料</p>'
    tiles = []
    for s, (x, y, w, h) in zip(xs, squarify([s["mcap"] for s in xs])):
        size = "lg" if w * h > 500 else "md" if w * h > 120 else "sm" if w * h > 40 and min(w, h) > 4 else "xs"
        tiles.append(f'<div class="mk-tile {size}" style="left:{x:.2f}%;top:{y:.2f}%;width:{w:.2f}%;height:{h:.2f}%;background:{heat_color(s["d1"])}" '
                     f'title="{e(s["name"])} {s["d1"]:+.2f}%｜市值 {money(s["mcap"])}"><b>{e(s["ticker"])}</b><span>{s["d1"]:+.2f}%</span></div>')
    return f'<div class="mk-tree us-tree">{"".join(tiles)}</div><p class="mk-note">方塊大小＝市值，顏色＝今日漲跌（紅漲綠跌）</p>'


# ---------- 重點個股 ----------

def rev_svg(series: list[list], w=220, h=56) -> str:
    if not series:
        return ""
    top = max(v for _, v in series) or 1
    bw = w / len(series)
    bars = "".join(f'<rect x="{i * bw + 2:.1f}" y="{h - 12 - v / top * (h - 16):.1f}" width="{bw - 4:.1f}" height="{max(v / top * (h - 16), 1):.1f}" rx="2"/>'
                   f'<text x="{i * bw + bw / 2:.1f}" y="{h - 1}">{e(d[2:7])}</text>' for i, (d, v) in enumerate(series))
    return f'<svg class="us-rev" viewBox="0 0 {w} {h}">{bars}</svg>'


def pos52(p) -> str:
    if p is None:
        return "—"
    return f'<span class="us-52" title="在 52 週區間的 {p}% 位置"><i style="left:{p}%"></i></span>'


def stock_row(s: dict) -> str:
    f = s.get("fin") or {}
    pe = "—" if s.get("pe") is None else f'{s["pe"]:.1f}'
    chips = "".join(f'<span class="us-chip">{e(p)}</span>' for p in s.get("whales", [])[:4])
    tw = "".join(f'<span class="us-chip tw">{e(t["name"])} {sp(t.get("chg_1d"))}</span>' for t in s.get("tw", []))
    detail = []
    if f:
        detail.append(f'<div><small>最近一季（{e(f["quarter_end"])} 止）營收</small><b>{money(f["rev_q"])}</b>{rev_svg(f.get("rev_q_series") or [])}</div>')
        detail.append(f'<div><small>近四季營收</small><b>{money(f.get("rev_ttm"))}</b><small>年增 {sp(f.get("rev_ttm_yoy"))}</small>'
                      f'<small>近四季淨利 {money(f.get("ni_ttm"))}・自由現金流 {money(f.get("fcf_ttm"))}</small></div>')
    else:
        detail.append('<div><small>財報</small><p class="muted">外國企業（申報 20-F／6-K）或 SEC 沒有標準化數字，本頁不計算，避免拿不同會計準則硬比。</p></div>')
    detail.append(f'<div><small>52 週區間</small><b>{s["lo52"]:,.2f} – {s["hi52"]:,.2f}</b><small>近 5 日 {sp(s.get("d5"))}・今年 {sp(s.get("ytd"))}</small></div>')
    if chips:
        detail.append(f'<div><small>持有的大佬（13F）</small><div class="us-chips">{chips}</div></div>')
    if tw:
        detail.append(f'<div><small>台股供應鏈（有出處的關係）</small><div class="us-chips">{tw}</div></div>')
    return (f'<details class="row us-row" data-live-us="{e(s["ticker"])}"><summary>'
            f'<span class="name">{stock_logo(s["ticker"], s["name"], "美股", "sm")}<span><b>{e(s["ticker"])}</b><small>{e(s["name"])}</small></span></span>'
            f'<span class="num"><b data-f="price">{s["price"]:,.2f}</b></span><span class="num" data-f="pct">{sp(s.get("d1"), 2)}</span>'
            f'<span class="num hide-sm">{sp(s.get("m1"))}</span><span class="num hide-sm">{pos52(s.get("pos52"))}</span>'
            f'<span class="num hide-sm">{money(s.get("mcap")).replace(" 美元", "")}</span>'
            f'<span class="num">{pe}</span>'
            f'<span class="num">{sp(f.get("rev_yoy"))}</span><span class="num hide-sm">{md(s.get("earnings"))}</span></summary>'
            f'<div class="row-body us-detail">{"".join(detail)}</div></details>')


def stock_tables(u: dict) -> str:
    by = {s["ticker"]: s for s in u["stocks"]}
    names = [g for g, ts in u["groups"].items() if any(t in by for t in ts)]
    head = ('<div class="thead"><span class="name">公司</span><span class="num">股價</span><span class="num">今日</span>'
            '<span class="num hide-sm">近 1 月</span><span class="num hide-sm">52 週位置</span><span class="num hide-sm">市值（美元）</span>'
            '<span class="num">本益比</span><span class="num">單季營收年增</span><span class="num hide-sm">下次財報</span></div>')
    panels = "".join(panel("grp", str(i), f'<div class="ctable us-table">{head}'
                           + "".join(stock_row(by[t]) for t in u["groups"][g] if t in by) + "</div>", i == 0)
                     for i, g in enumerate(names))
    return (tabs("grp", [(str(i), g) for i, g in enumerate(names)], "0") + panels
            + '<p class="mk-note">本益比＝市值 ÷ 近四季淨利（SEC 申報）；單季營收年增＝最近一季對去年同季。點列可展開營收走勢、現金流、持有大佬與台股供應鏈。</p>')


# ---------- 財報行事曆、申報 ----------

def earnings_calendar(stocks: list[dict], today: str, days: int = 35) -> str:
    end = date.fromordinal(date.fromisoformat(today).toordinal() + days).isoformat()
    xs = sorted((s for s in stocks if s.get("earnings") and today <= s["earnings"] <= end), key=lambda s: (s["earnings"], -(s.get("mcap") or 0)))
    if not xs:
        return '<p class="empty">接下來沒有追蹤中的公司公布財報</p>'
    by: dict[str, list[dict]] = {}
    for s in xs:
        by.setdefault(s["earnings"], []).append(s)
    cols = "".join(f'<div class="us-day"><b>{md(d)}</b>' + "".join(
        f'<span>{stock_logo(s["ticker"], s["name"], "美股", "xs")}{e(s["ticker"])}</span>' for s in ss) + "</div>" for d, ss in by.items())
    return f'<div class="us-cal">{cols}</div><p class="mk-note">日期為 Yahoo Finance 預估，以公司正式公告為準（美東時間，台灣通常是隔天早上）</p>'


FORM_LABEL = {"10-Q": "季報 10-Q", "10-K": "年報 10-K", "20-F": "年報 20-F", "8-K": "重大訊息 8-K", "8-K/A": "重大訊息更正"}


def filings(fs: list[dict]) -> str:
    if not fs:
        return '<p class="empty">最近沒有新申報</p>'
    lis = "".join(
        f'<li><span class="time">{md(f["filed"])}</span>{stock_logo(f["ticker"], f["name"], "美股", "xs")}<b>{e(f["ticker"])}</b>'
        f'<span class="pill">{e(FORM_LABEL.get(f["form"], f["form"]))}</span><span>{e("、".join(f["items"]))}</span>'
        f'<a href="{e(f["url"])}" target="_blank" rel="noopener"><img class="ui-ico xs" src="/ui/doc.svg" alt=""> SEC 原文</a></li>' for f in fs[:30])
    return f'<ul class="us-filings">{lis}</ul>'


def render(u: dict | None, hero, section, today: str) -> str:
    if not u:
        return hero("美股", "資料準備中", "") + '<main class="wrap"><p class="empty">美股資料第一次產生後會出現在這裡</p></main>'
    d = (u["indices"] or [{}])[0].get("date")
    body = hero("美股", f"{md(d)} 收盤" if d else "美股", "指數、類股、權值股與 SEC 官方財報，盤中報價每分鐘更新。",
                '<p class="hero-note">報價：Yahoo Finance；財報與申報：SEC EDGAR 官方資料。研究素材整理，不是買賣建議。</p>')
    body += '<main class="wrap">'
    body += section("指數與利率", index_cards(u["indices"]))
    body += section("類股強弱", sector_bars(u["sectors"]))
    body += section("市值熱力圖", heatmap(u["stocks"]), f'{len(u["stocks"])} 檔追蹤中的美股')
    body += section("重點個股", stock_tables(u), "點列展開看財報細節")
    body += section("財報行事曆", earnings_calendar(u["stocks"], today), "接下來 5 週")
    body += section("近期 SEC 申報", filings(u["filings"]), "近 3 週・季報、年報與重大訊息（只列有實質 item 的 8-K）")
    body += f'<p class="mk-note">資料更新於 {e(floor5(u["generated_at"], "%Y-%m-%d %H:%M"))}</p></main>' + TAB_SCRIPT
    return body
