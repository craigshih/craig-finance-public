"""Discord 推播：把網站各區的重點做成一行一則、可點的標題清單，用 webhook 貼到頻道。

資料來源：網站的公開 /feed/*.json（跟外部工具拿的是同一份），匯率在推播當下另向 Yahoo 拿即時價。
只放公開資料整理；每日總經、每週研究等私人來源的內容只給連結、不放內文。
DISCORD_WEBHOOK_URL 沒設定就只印出訊息、不送出；加 --dry-run 也一樣。
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

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


def lines(pick: dict | None, market: dict | None, us: dict | None, fx: dict) -> list[str]:
    out = []
    if fx:
        parts = [f'{name} {fx[s]["price"] * unit:.3f}（{fx[s]["pct"]:+.2f}%）' for s, name, unit in FX if s in fx]
        out.append(link("台幣匯率　" + "・".join(parts), "market/index.html"))
    if pick:
        out.append(link(f'每日一檔 {pick["date"][5:]}：{pick["name"]}（{pick["code"]}）{(pick.get("story") or {}).get("title", "")}',
                        f'pick/{pick["date"]}.html'))
    if market and market.get("summary"):
        out.append(link(f'台股收盤 {(market.get("date") or "")[5:]}：{market["summary"].split("；")[0]}', "market/index.html"))  # 只留第一句當標題
    if us and us.get("indices"):
        ix = "、".join(f'{i["name"]} {i["d1"]:+.2f}%' for i in us["indices"][:3] if i.get("d1") is not None)
        out.append(link(f'美股 {(us["indices"][0].get("date") or "")[5:]}：{ix}', "us/index.html"))
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
