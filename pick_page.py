"""
「每日一檔」頁面：今天的推薦（提問式標題 → 一句話 → 發展歷史 → 產業位置 → 最近動態 → 機會與風險 → 名詞小辭典 → 資料來源），
加上過去的推薦清單。資料來自 daily_pick.py 的 data/daily_pick/{date}.json。
"""

import json
from html import escape
from pathlib import Path

from visuals import clean_names, stock_logo

DISCLAIMER = ("本文由 AI 依公開資料（證交所、櫃買中心、維基百科、鉅亨網、已查證的供應鏈報導）整理，僅供學習研究，"
              "不構成任何投資建議；含有資料裡查不到的數字的句子已自動刪除，但仍可能有誤，請以原始資料為準。")


def e(x) -> str:
    return escape(str(x if x is not None else ""))


def load_all(d: Path) -> list[dict]:
    out = []
    for f in sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []:
        try:
            out.append(clean_names(json.loads(f.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError):
            pass
    return out


def snapshot(p: dict) -> str:
    k = p.get("snapshot") or {}
    cells = [("收盤", f'{k["close"]:,}' if k.get("close") else None),
             (f'{k.get("rev_month") or ""} 月營收年增', f'{k["rev_yoy"]:+.1f}%' if k.get("rev_yoy") is not None else None),
             ("毛利率", f'{k["gross"]:.1f}%' if k.get("gross") is not None else None),
             ("本益比", f'{k["pe"]:.1f}' if k.get("pe") else None),
             ("殖利率", f'{k["yield"]:.2f}%' if k.get("yield") else None)]
    tiles = "".join(f'<div class="pk-tile"><small>{e(a)}</small><b>{e(b)}</b></div>' for a, b in cells if b)
    return f'<div class="pk-tiles">{tiles}</div>' if tiles else ""


def article(p: dict, prefix: str = "../") -> str:
    s = p["story"]
    li = lambda xs: "".join(f"<li>{e(x)}</li>" for x in xs)
    hist = "".join(f'<li><b>{e(h["when"])}</b><span>{e(h["what"])}</span></li>' for h in s["history"])
    terms = "".join(f'<li><b>{e(t["term"])}</b><span>{e(t["plain"])}</span>'
                    f'<a href="{e(t["url"])}" target="_blank" rel="noopener">{e(t.get("url_label") or "資料來源")} ↗</a></li>' for t in s["terms"])
    src = "".join(f'<li><a href="{e(x["url"])}" target="_blank" rel="noopener">{e(x["label"])}</a></li>' for x in p["sources"])
    why = p.get("why") or {}
    reason = "、".join(x for x in [
        f'今天早報點名 {why["digest_mentions"]} 次' if why.get("digest_mentions") else "",
        f'近 7 天新聞 {why["news_7d"]} 篇' if why.get("news_7d") else "",
        "每週研究候選" if why.get("weekly") else "", "供應鏈地圖台廠" if why.get("supply") else ""] if x)
    block = lambda title, body, cls="": f'<section class="pk-sec {cls}"><h2>{title}</h2>{body}</section>' if body else ""
    return (
        f'<article class="pick-article">'
        f'<header class="pk-head">{stock_logo(p["code"], p["name"], p["market"], "xl")}'
        f'<div><p class="pk-kicker">{e(p["name"])}・{e(p["code"])}・{e(p["market"])}・{e(p.get("industry") or "")}</p>'
        f'<h1>{e(s["title"])}</h1><p class="pk-one">{e(s["one_liner"])}</p></div></header>'
        + snapshot(p)
        + (f'<p class="pk-why">為什麼是它：{e(reason)}</p>' if reason else "")
        + block("發展歷史", f'<ol class="pk-time">{hist}</ol>' if hist else "")
        + block("產業位置", f'<p>{e(s["industry"])}</p>' if s["industry"] else "")
        + block("最近在做什麼", f'<ul>{li(s["now"])}</ul>' if s["now"] else "")
        + '<div class="pk-two">'
        + block("未來的機會", f'<ul>{li(s["opportunities"])}</ul>' if s["opportunities"] else "", "up")
        + block("需要注意的風險", f'<ul>{li(s["risks"])}</ul>' if s["risks"] else "", "down")
        + "</div>"
        + block("之後可以追蹤", f'<ul>{li(s["watch"])}</ul>' if s["watch"] else "")
        + block("名詞小辭典", f'<ul class="pk-terms">{terms}</ul>' if terms else "")
        + block("資料來源", f'<ul class="pk-src">{src}</ul>')
        + f'<p class="pk-legal">{e(DISCLAIMER)}</p></article>'
    )


def archive(picks: list[dict], current: str | None = None) -> str:
    items = "".join(
        f'<a class="pk-old{" on" if p["date"] == current else ""}" href="{e(p["date"])}.html">{stock_logo(p["code"], p["name"], p["market"], "sm")}'
        f'<span><small>{e(p["date"])}</small><b>{e(p["name"])}</b><i>{e(p["story"]["title"])}</i></span></a>' for p in picks)
    return f'<div class="pk-archive">{items}</div>'


def home_card(p: dict) -> str:
    s = p["story"]
    return (f'<a class="pk-card" href="pick/{e(p["date"])}.html">{stock_logo(p["code"], p["name"], p["market"], "lg")}'
            f'<span><small>每日一檔・{e(p["date"])}・{e(p["name"])}（{e(p["code"])}）</small><b>{e(s["title"])}</b>'
            f'<i>{e(s["one_liner"])}</i></span><em>看完整介紹 →</em></a>')
