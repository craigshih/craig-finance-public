"""公開資料出口（/feed/*.json）：給朋友串 Discord 之類的外部工具用。

只放「本來就是公開資料整理」的內容：每日一檔、台股收盤、美股。
任何跟站長有關的東西（持股、觀察清單、研究候選、每週研究、早報摘要、選股挑選依據）一律不放。
Cloudflare Access 要對 /feed/* 開繞過規則，外部才讀得到。
"""
import json
from pathlib import Path

DISCLAIMER = "資料整理自證交所、櫃買中心、期交所、Yahoo Finance、SEC 等公開來源，AI 文字僅供學習研究，不構成投資建議。"


def _drop(d: dict, *keys) -> dict:
    return {k: v for k, v in d.items() if k not in keys}


def _yi(x: float) -> str:
    return f'{"買超" if x >= 0 else "賣超"} {abs(x):,.1f} 億'


def pick_feed(pk: dict, text_messages: list[str]) -> dict:
    # why（挑選依據）會透露站長的研究清單，不放；寄信、推播紀錄也不放
    keep = ("date", "code", "name", "market", "industry", "story", "sources", "snapshot", "generated_at")
    out = {k: pk.get(k) for k in keep}
    out["text"] = text_messages  # 已排好版的純文字，每則都在 Discord 2000 字上限內，可直接貼
    return out


def market_summary(m: dict, extra: dict | None) -> str:
    ix = {i["ticker"]: i for i in m.get("indices") or []}
    tw = ix.get("^TWII")
    if not tw:
        return ""
    s = f'台股加權收 {tw["close"]:,.0f}，{"上漲" if tw["chg"] >= 0 else "下跌"} {abs(tw["chg"]):,.0f} 點（{tw["chg_pct"]:+.2f}%）'
    b = m.get("breadth") or {}
    if b:
        s += f'；{b["up"]} 漲／{b["down"]} 跌，漲停 {b["limit_up"]}、跌停 {b["limit_down"]}'
    h = (m.get("history") or [None])[-1]
    if h and h["date"] == tw["date"]:
        s += f'。外資{_yi(h["foreign"])}、投信{_yi(h["trust"])}、自營商{_yi(h["dealer"])}'
    themes = sorted(m.get("themes") or [], key=lambda t: -t["pct"])
    if themes:
        s += "。最強族群：" + "、".join(f'{t["name"]} {t["pct"]:+.1f}%' for t in themes[:3])
    c = (extra or {}).get("contrib")
    if c and c.get("date") == tw["date"]:
        s += f'。台積電貢獻 {c["tsmc"]:+.0f} 點'
    return s + "。"


def market_feed(m: dict | None, extra: dict | None) -> dict | None:
    if not m or not m.get("indices"):
        return None
    extra = extra or {}
    val = extra.get("valuation")
    fut = extra.get("futures")
    return {
        "generated_at": m.get("generated_at"),
        "date": m.get("quote_date") or next((i["date"] for i in m["indices"] if i["ticker"] == "^TWII"), None),
        "summary": market_summary(m, extra),
        "indices": [_drop(i, "ohlc") for i in m["indices"]],
        "breadth": m.get("breadth"),
        "institutions": (m.get("history") or [None])[-1],  # 三大法人（億元）與融資餘額
        "industries": m.get("industries"),
        "themes": m.get("themes"),
        "strong": m.get("strong"),  # d／w／m：單日、一週、一個月強勢股
        "big_holders": m.get("big_holders"),  # 集保千張大戶持股比例變化（公開資料，不是站長的持股）
        "warnings": m.get("warnings"),
        "ex_dividends": m.get("ex_dividends"),
        "index_contribution": extra.get("contrib"),
        "valuation": _drop(val, "series") if val else None,
        "futures": _drop(fut, "pc_series") if fut else None,
    }


def us_feed(u: dict | None) -> dict | None:
    if not u or not u.get("indices"):
        return None
    strip = lambda xs: [_drop(x, "spark", "rev") for x in xs or []]
    return {
        "generated_at": u.get("generated_at"),
        "indices": strip(u.get("indices")),
        "sectors": strip(u.get("sectors")),
        "groups": u.get("groups"),
        "stocks": strip(u.get("stocks")),
        "filings": u.get("filings"),
    }


def write_all(out: Path, picks: list[dict], line_messages, market: dict | None, extra: dict | None, us: dict | None) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    if picks:
        files["daily-pick.json"] = pick_feed(picks[0], line_messages(picks[0]))
        files["daily-pick-archive.json"] = [{k: p.get(k) for k in ("date", "code", "name", "industry")} for p in picks[:60]]
    if (mk := market_feed(market, extra)):
        files["market.json"] = mk
    if (us_ := us_feed(us)):
        files["us.json"] = us_
    files["index.json"] = {
        "about": "Craig 財經站公開資料。每天收盤後與早上 9 點左右更新。",
        "disclaimer": DISCLAIMER,
        "endpoints": {
            "daily-pick.json": "今日的每日一檔（含 text：可直接貼的純文字訊息）",
            "daily-pick-archive.json": "最近 60 天的每日一檔清單",
            "market.json": "台股收盤：指數、漲跌家數、三大法人、族群、強勢股、注意處置股、除權息、估值、期貨籌碼",
            "us.json": "美股：主要指數、類股 ETF、權值股、SEC 最新申報",
        },
    }
    for name, data in files.items():
        (out / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return sorted(files)
