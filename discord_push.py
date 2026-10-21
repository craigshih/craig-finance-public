"""Discord 推播：把網站各區的重點做成一行一則、可點的標題清單，用 webhook 貼到頻道。

資料來源：網站的公開 /feed/*.json（跟外部工具拿的是同一份），匯率在推播當下另向 Yahoo 拿即時價。
有 GROQ_API_KEY 時請 AI 把每區寫成「結論 → 可能影響」的一行標題，沒有或沒通過檢查就用固定句型。
只放公開資料整理；每日總經、每週研究等私人來源的內容只給連結、不放內文。
DISCORD_WEBHOOK_URL 沒設定就只印出訊息、不送出；加 --dry-run 也一樣。
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests

from picks import has_banned  # 跟每日觀察標的共用同一份禁用字（目標價、買賣指示）

SITE = os.environ.get("SITE_URL", "https://craig-finance.pages.dev").rstrip("/")
TAIPEI = timezone(timedelta(hours=8))
UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)"
FX = [("TWD=X", "美元", 1), ("JPYTWD=X", "100 日圓", 100), ("EURTWD=X", "歐元", 1)]  # 日圓用 100 日圓計價比較好讀


def get_json(url: str):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"⚠️ {url} 讀取失敗：{exc}", file=sys.stderr)
        return None


def fx_quotes() -> dict:
    """Yahoo spark：現價與前一日收盤（跟 functions/_lib/live.js 用同一個來源）。"""
    syms = ",".join(s for s, *_ in FX)
    d = get_json(f"https://query1.finance.yahoo.com/v7/finance/spark?range=1d&interval=1d&symbols={requests.utils.quote(syms)}")
    out = {}
    for r in ((d or {}).get("spark") or {}).get("result") or []:
        meta = ((r.get("response") or [{}])[0]).get("meta") or {}
        price, prev = meta.get("regularMarketPrice"), meta.get("chartPreviousClose")
        if price and prev:
            out[r["symbol"]] = {"price": price, "pct": (price / prev - 1) * 100}
    return out


def link(text: str, path: str) -> str:
    return f"• [{text}]({SITE}/{path})"


def facts(pick: dict | None, market: dict | None, us: dict | None, fx: dict) -> dict:
    """給 AI 的資料：只有公開 feed 與匯率裡的數字。AI 標題裡的數字必須出現在這裡（見 numbers_ok）。"""
    f = {}
    if fx:
        f["fx"] = {name: {"價格": round(fx[s]["price"] * unit, 3), "漲跌%": round(fx[s]["pct"], 2)} for s, name, unit in FX if s in fx}
    if market and market.get("summary"):
        b, ins, fut = market.get("breadth") or {}, market.get("institutions") or {}, market.get("futures") or {}
        f["market"] = {"資料日": market.get("date"), "總結": market["summary"],
                       "上漲家數": b.get("up"), "下跌家數": b.get("down"),
                       "三大法人（億元）": ins and {"資料日": ins.get("date"), "外資": ins.get("foreign"), "投信": ins.get("trust"), "自營商": ins.get("dealer")},
                       "外資台指期淨未平倉（口）": fut.get("foreign_tx")}
    val = (market or {}).get("valuation")
    if val:
        f["valuation"] = {"本益比": val.get("pe"), "本益比在近10年的百分位": (val.get("pct") or {}).get("pe"),
                          "近10年本益比中位數": (val.get("median") or {}).get("pe"), "殖利率%": val.get("yield")}
    if us and us.get("indices"):
        sec = sorted((s for s in us.get("sectors") or [] if s.get("d1") is not None), key=lambda s: -s["d1"])
        f["us"] = {"資料日": us["indices"][0].get("date"),
                   "指數": [{"名稱": i["name"], "當日%": i.get("d1"), "近5日%": i.get("d5")} for i in us["indices"][:5]],
                   "最強類股": [{s["name"]: s["d1"]} for s in sec[:2]], "最弱類股": [{s["name"]: s["d1"]} for s in sec[-2:]]}
    if pick:
        st = pick.get("story") or {}
        f["pick"] = {"公司": f'{pick["name"]}（{pick["code"]}）', "標題": st.get("title"), "一句話": st.get("one_liner"),
                     "近況": st.get("now"), "觀察重點": st.get("watch")}
    return f


PROMPT = """你是財經網站的編輯。依下面 JSON 資料，替每個區塊寫一行 Discord 標題。
格式：「一句結論 → 這個結論可能帶來的影響」，語氣直接，繁體中文，60 字以內。
規則：
- 只能用資料裡出現的數字，不要自己計算新數字，也不要補充資料以外的事實
- 「影響」寫市場結構、風險或接下來要留意的事；不預測漲跌，不給買賣建議，不提目標價
- 不要重複區塊名稱或日期（程式會自己加）
範例：台股是權值股撐起來的上漲 → 一旦台積電轉弱，指數缺少其他股票承接，回檔幅度可能放大
回傳 JSON，key 只能是資料裡有的區塊（fx、market、valuation、us、pick），值是那一行標題。

資料：
{data}"""


def numbers_ok(text: str, data: str) -> bool:
    """標題裡每個數字都要能在資料裡找到（允許 AI 四捨五入到較少位數）。"""
    have = {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", data)}
    for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        d = len(n.split(".")[1]) if "." in n else 0
        v = float(n.replace(",", ""))
        if not any(round(h, d) == v or round(-h, d) == v for h in have):
            return False
    return True


def ai_headlines(f: dict) -> dict:
    """一次呼叫 Groq 拿所有區塊的標題；沒有金鑰、失敗、含禁用字或亂編數字的區塊就不採用（改用固定句型）。"""
    key = (os.environ.get("GROQ_API_KEY") or "").strip()
    if not key or not f:
        return {}
    data = json.dumps(f, ensure_ascii=False)
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                          json={"model": os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b", "reasoning_effort": "low",
                                "max_completion_tokens": 2000, "response_format": {"type": "json_object"},
                                "messages": [{"role": "user", "content": PROMPT.format(data=data)}]}, timeout=90)
        r.raise_for_status()
        got = json.loads(r.json()["choices"][0]["message"]["content"])
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        print(f"⚠️ AI 標題失敗，改用固定句型：{exc}", file=sys.stderr)
        return {}
    out = {}
    for k, v in got.items():
        v = str(v).strip()
        if k not in f or not v or len(v) > 120:
            continue
        if has_banned(v) or not numbers_ok(v, data):
            print(f"⚠️ {k} 的 AI 標題沒通過檢查，改用固定句型：{v}", file=sys.stderr)
            continue
        out[k] = v
    return out


def lines(pick: dict | None, market: dict | None, us: dict | None, fx: dict) -> list[str]:
    f = facts(pick, market, us, fx)
    ai = ai_headlines(f)
    rows = []  # (區塊, 前綴, AI 失敗時的固定句型, 連結)
    if fx:
        quotes = "・".join(f'{name} {fx[s]["price"] * unit:.3f}（{fx[s]["pct"]:+.2f}%）' for s, name, unit in FX if s in fx)
        rows.append(("fx", f"台幣匯率 {quotes}", "", "fx/index.html"))
    if "market" in f:
        rows.append(("market", f'台股 {(market.get("date") or "")[5:]}', market["summary"].split("；")[0], "market/index.html"))
    if "valuation" in f:
        v = f["valuation"]
        rows.append(("valuation", "台股估值", f'本益比 {v["本益比"]} 倍，在近 10 年 {v["本益比在近10年的百分位"]}% 的位置', "market/index.html"))
    if "us" in f:
        ix = "、".join(f'{i["名稱"]} {i["當日%"]:+.2f}%' for i in f["us"]["指數"][:3] if i["當日%"] is not None)
        rows.append(("us", f'美股 {(f["us"]["資料日"] or "")[5:]}', ix, "us/index.html"))
    if pick:
        rows.append(("pick", f'每日一檔 {pick["date"][5:]}', f'{f["pick"]["公司"]}{f["pick"]["標題"] or ""}', f'pick/{pick["date"]}.html'))
    out = [link("｜".join(x for x in (prefix, ai.get(k) or fallback) if x), path) for k, prefix, fallback, path in rows]
    out += [link("每日總經", "daily/index.html"), link("供應鏈地圖", "supply/index.html"), link("大佬持股", "whales/index.html")]
    return out


def payload(body: list[str], now: datetime) -> dict:
    desc = ""
    for ln in body:  # embed 內文上限 4096 字，超過的整行丟掉
        if len(desc) + len(ln) + 1 > 4000:
            break
        desc += ln + "\n"
    return {"embeds": [{"title": f'Craig 財經站重點・{now:%m/%d %H:%M}', "url": SITE, "description": desc.strip(),
                        "footer": {"text": "資料整理自公開來源，不構成投資建議"}}]}


def main() -> None:
    feed = lambda n: get_json(f"{SITE}/feed/{n}")  # noqa: E731
    p = payload(lines(feed("daily-pick.json"), feed("market.json"), feed("us.json"), fx_quotes()), datetime.now(TAIPEI))
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not hook or "--dry-run" in sys.argv:
        print(json.dumps(p, ensure_ascii=False, indent=2))
        return
    requests.post(hook, json=p, timeout=30).raise_for_status()
    print("✅ 已送出 Discord")


if __name__ == "__main__":
    main()
