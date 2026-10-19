"""
今日觀察標的：每天依透明規則選出台股、美股各一檔，再用四種「模擬投資角色」寫觀點。

這是研究素材，不是買進建議：選股規則與數字全部公開在網頁上，角色觀點一定包含風險面，
並禁止出現目標價與買賣指示（見 BANNED_WORDS）。

台股（上市）
  1. 資金流：證交所三大法人買賣超（T86），取最近 5 個交易日「外資＋投信」的淨買超，
     乘上收盤價換算成金額。
  2. 產業趨勢：把淨買超金額依產業加總，取資金淨流入最多的產業。
  3. 個股：該產業裡淨買超金額最大、5 天中至少 3 天是買超、收盤價站上 20 日均線的公司
     （排除 ETF、成交值低於 1 億的股票）。
美股
  1. 產業趨勢：11 個 SPDR 類股 ETF 近 20 日報酬減去 SPY，取相對最強的類股。
  2. 資金流：該類股成分大型股的 Chaikin Money Flow（20 日）與量能比（5 日均量 / 50 日均量）。
  3. 個股：收盤價在 50 日均線之上、CMF > 0 的股票中，綜合排名最前面的一檔。

輸出 data/picks/{台股交易日}.json，由 workflow commit 回 repo，build.py 讀取顯示。
"""

import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "data" / "picks"
TAIPEI = timezone(timedelta(hours=8))
UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)"

GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b"
FINMIND_TOKEN = (os.environ.get("FINMIND_TOKEN") or "").strip()

TWSE_T86 = "https://www.twse.com.tw/rwd/zh/fund/T86"
TWSE_OPEN = "https://openapi.twse.com.tw/v1"
CNYES_RSS = "https://news.cnyes.com/rss/v1/news/category/{}"

US_SECTORS = {
    "XLK": ("科技", ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "AMD", "CRM", "ADBE"]),
    "XLC": ("通訊服務", ["GOOGL", "META", "NFLX", "DIS", "TMUS", "VZ"]),
    "XLY": ("非必需消費", ["AMZN", "TSLA", "HD", "MCD", "NKE", "BKNG"]),
    "XLF": ("金融", ["JPM", "V", "MA", "BAC", "GS", "BRK-B"]),
    "XLV": ("醫療保健", ["LLY", "UNH", "JNJ", "ABBV", "MRK", "ISRG"]),
    "XLI": ("工業", ["GE", "CAT", "RTX", "HON", "UBER", "BA"]),
    "XLE": ("能源", ["XOM", "CVX", "COP", "EOG", "SLB"]),
    "XLP": ("必需消費", ["WMT", "COST", "PG", "KO", "PEP"]),
    "XLU": ("公用事業", ["NEE", "SO", "DUK", "CEG"]),
    "XLB": ("原物料", ["LIN", "SHW", "FCX", "NEM"]),
    "XLRE": ("不動產", ["PLD", "AMT", "EQIX", "WELL"]),
}

from investors import INVESTORS

# 四位投資人的模擬框架（跟每週基本面分析同一套）：(id, 名字, 分析重點, 說話風格)
PERSONAS = [(i["id"], i["name"], i["focus"], i["voice"]) for i in INVESTORS]
# 叫讀者做交易的用語；「法人買進/賣出」這種描述資料的用法不算，所以不擋「買進」「賣出」本身
BANNED_WORDS = ("目標價", "建議買", "建議賣", "逢低買", "可以買", "值得買", "應該買", "加碼", "減碼", "停損", "停利", "進場", "出場", "必漲", "保證",
                # 模擬角色不能假裝自己真的有部位
                "我買了", "我持有", "我賣了", "我加碼", "我們持有", "我的部位")


# 指標的中文名稱與解讀方式：給 AI 看（避免誤讀），也用在網頁顯示
METRIC_LABELS = {
    "foreign_lots_5d": ("外資 5 日買賣超", "張", "正值＝外資淨買進"),
    "trust_lots_5d": ("投信 5 日買賣超", "張", "正值＝投信淨買進"),
    "buy_days_5d": ("法人淨買超天數", "／5 天", "外資＋投信合計為買超的天數"),
    "net_value_5d_100m": ("法人 5 日淨買超金額", "億元", "外資＋投信淨買超股數 × 收盤價"),
    "industry_rank": ("產業資金流入排名", "", "1＝全市場資金淨流入最多的產業"),
    "industry_net_value_100m": ("產業 5 日淨流入", "億元", "該產業所有個股法人淨買超金額加總"),
    "rev_m_yoy_pct": ("最新月營收年增率", "%", "跟去年同月比"),
    "rev_month": ("營收月份", "", "民國年月"),
    "pe": ("本益比", "倍", "股價 ÷ 近四季每股盈餘，越高代表市場預期越高、也越貴"),
    "dividend_yield_pct": ("殖利率", "%", "近一年現金股利 ÷ 股價"),
    "ret_20d_pct": ("近 20 日漲跌", "%", ""),
    "above_ma20": ("站上 20 日均線", "", "收盤價高於近 20 日平均"),
    "above_ma60": ("站上 60 日均線", "", "收盤價高於近 60 日平均"),
    "from_60d_high_pct": ("距 60 日高點", "%", "負值＝目前低於高點多少"),
    "sector_rank": ("類股相對強度排名", "", "1＝11 個類股中近 20 日相對大盤最強"),
    "sector_rel_20d_pct": ("類股近 20 日超額報酬", "%", "類股 ETF 報酬減去 SPY 報酬"),
    "cmf_20": ("CMF 資金流（20 日）", "", "介於 -1～1，大於 0 代表收盤多落在當日高檔、資金淨流入，越大越強"),
    "vol_ratio_5_50": ("量能比（5 日／50 日均量）", "倍", "大於 1＝近期放量，小於 1＝近期量縮"),
    "above_ma50": ("站上 50 日均線", "", ""),
    "above_ma200": ("站上 200 日均線", "", "長期趨勢向上的常見指標"),
    "from_52w_high_pct": ("距 52 週高點", "%", "負值＝目前低於高點多少"),
    "forward_pe": ("預估本益比", "倍", "以分析師預估的未來盈餘計算"),
}


def describe_metrics(metrics: dict) -> str:
    lines = []
    for k, v in metrics.items():
        if v is None or k not in METRIC_LABELS:
            continue
        label, unit, note = METRIC_LABELS[k]
        value = ("是" if v else "否") if isinstance(v, bool) else f"{v}{unit}"
        lines.append(f"- {label}：{value}" + (f"（{note}）" if note else ""))
    return "\n".join(lines)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


# ---------- 台股 ----------

def t86(day: date) -> list | None:
    r = requests.get(TWSE_T86, params={"date": day.strftime("%Y%m%d"), "selectType": "ALLBUT0999", "response": "json"},
                     headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    d = r.json()
    return d["data"] if d.get("stat") == "OK" and d.get("data") else None


def recent_t86(n: int = 5) -> list[tuple[date, list]]:
    """往回找最近 n 個有資料的交易日（假日、當天尚未公布會跳過）。"""
    days, day = [], datetime.now(TAIPEI).date()
    for _ in range(14):
        if day.weekday() < 5:
            rows = t86(day)
            time.sleep(3)  # 對證交所客氣一點
            if rows:
                days.append((day, rows))
                if len(days) == n:
                    break
        day -= timedelta(days=1)
    return days


def finmind_prices(code: str, start: date) -> list[dict]:
    if not FINMIND_TOKEN:
        return []
    r = requests.get("https://api.finmindtrade.com/api/v4/data",
                     params={"dataset": "TaiwanStockPrice", "data_id": code, "start_date": start.isoformat()},
                     headers={"Authorization": f"Bearer {FINMIND_TOKEN}"}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def sum_flows(days: list[tuple[date, list]]) -> dict[str, dict]:
    flows: dict[str, dict] = {}
    for _, rows in days:
        for r in rows:
            code = r[0].strip()
            f = flows.setdefault(code, {"code": code, "name": r[1].strip(), "foreign": 0, "trust": 0, "buy_days": 0})
            foreign, trust = _num(r[4]) or 0, _num(r[10]) or 0
            f["foreign"] += foreign
            f["trust"] += trust
            f["buy_days"] += foreign + trust > 0
    return flows


def save_flows(trade_date: date, days: list, flows: dict) -> None:
    """全部個股的 5 日法人買賣超另外存一份，給供應鏈地圖用（不必再打一次證交所）。"""
    flows_dir = ROOT / "data" / "flows"
    flows_dir.mkdir(parents=True, exist_ok=True)
    (flows_dir / "latest.json").write_text(json.dumps({
        "date": trade_date.isoformat(), "days": len(days),
        "codes": {c: {"foreign_lots": round(f["foreign"] / 1000), "trust_lots": round(f["trust"] / 1000), "buy_days": f["buy_days"]}
                  for c, f in flows.items()},
    }, ensure_ascii=False), encoding="utf-8")


def refresh_flows() -> None:
    days = recent_t86()
    if days:
        save_flows(days[0][0], days, sum_flows(days))
        print(f"✅ 法人資料更新到 {days[0][0]}")


def pick_tw() -> dict | None:
    days = recent_t86()
    if len(days) < 3:
        log("⚠️ 證交所三大法人資料不足，略過台股")
        return None
    trade_date = days[0][0]

    quotes = {r["Code"]: r for r in requests.get(f"{TWSE_OPEN}/exchangeReport/STOCK_DAY_ALL", headers={"User-Agent": UA}, timeout=30).json()}
    revenue = {r["公司代號"]: r for r in requests.get(f"{TWSE_OPEN}/opendata/t187ap05_L", headers={"User-Agent": UA}, timeout=30).json()}
    valuation = {r["Code"]: r for r in requests.get(f"{TWSE_OPEN}/exchangeReport/BWIBBU_ALL", headers={"User-Agent": UA}, timeout=30).json()}

    flows = sum_flows(days)
    save_flows(trade_date, days, flows)

    stocks = []
    for code, f in flows.items():
        q, rev = quotes.get(code), revenue.get(code)
        if not (re.fullmatch(r"[1-9]\d{3}", code) and q and rev):
            continue  # 只看一般股票，排除 ETF、權證、特別股
        close, value = _num(q.get("ClosingPrice")), _num(q.get("TradeValue"))
        if not close or close < 10 or not value or value < 1e8:
            continue
        f.update(close=close, industry=rev.get("產業別"), net_value=(f["foreign"] + f["trust"]) * close,
                 rev_m_yoy=_num(rev.get("營業收入-去年同月增減(%)")), rev_month=rev.get("資料年月"),
                 pe=_num(valuation.get(code, {}).get("PEratio")), dividend_yield=_num(valuation.get(code, {}).get("DividendYield")))
        stocks.append(f)

    by_industry: dict[str, dict] = {}
    for s in stocks:
        g = by_industry.setdefault(s["industry"], {"industry": s["industry"], "net_value": 0, "n": 0})
        g["net_value"] += s["net_value"]
        g["n"] += 1
    industries = sorted((g for g in by_industry.values() if g["n"] >= 3), key=lambda g: -g["net_value"])

    for rank, ind in enumerate(industries[:3], 1):
        cands = sorted((s for s in stocks if s["industry"] == ind["industry"] and s["buy_days"] >= 3 and s["net_value"] > 0),
                       key=lambda s: -s["net_value"])
        for s in cands[:4]:
            prices = finmind_prices(s["code"], trade_date - timedelta(days=120))
            closes = [p["close"] for p in prices if p.get("close")]
            if len(closes) >= 60:
                ma20, ma60 = sum(closes[-20:]) / 20, sum(closes[-60:]) / 60
                if closes[-1] < ma20:
                    continue  # 法人在買但股價還在 20 日線下，趨勢不明確，換下一檔
                s.update(ma20=ma20, ma60=ma60, ret_20d=closes[-1] / closes[-21] - 1, high_60d=max(closes[-60:]),
                         spark=[round(c, 2) for c in closes[-60:]])
            elif FINMIND_TOKEN:
                continue
            return {
                "market": "台股", "code": s["code"], "name": s["name"], "industry": s["industry"], "data_date": trade_date.isoformat(),
                "price": s["close"], "spark": s.get("spark"),
                "metrics": {
                    "foreign_lots_5d": round(s["foreign"] / 1000), "trust_lots_5d": round(s["trust"] / 1000),
                    "buy_days_5d": s["buy_days"], "net_value_5d_100m": round(s["net_value"] / 1e8, 2),
                    "industry_rank": rank, "industry_net_value_100m": round(ind["net_value"] / 1e8, 1),
                    "rev_m_yoy_pct": s["rev_m_yoy"], "rev_month": s["rev_month"], "pe": s["pe"], "dividend_yield_pct": s["dividend_yield"],
                    "ret_20d_pct": round(s["ret_20d"] * 100, 1) if "ret_20d" in s else None,
                    "above_ma20": True if "ma20" in s else None, "above_ma60": s["close"] >= s["ma60"] if "ma60" in s else None,
                    "from_60d_high_pct": round((s["close"] / s["high_60d"] - 1) * 100, 1) if "high_60d" in s else None,
                },
                "top_industries": [{"industry": g["industry"], "net_value_100m": round(g["net_value"] / 1e8, 1)} for g in industries[:5]],
            }
    log("⚠️ 前三大資金流入產業都沒有符合條件的個股")
    return None


# ---------- 美股 ----------

def _cmf(df, n=20) -> float | None:
    rng = (df["High"] - df["Low"]).replace(0, float("nan"))
    mfv = ((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / rng * df["Volume"]
    vol = df["Volume"].tail(n).sum()
    return float(mfv.tail(n).sum() / vol) if vol else None


def pick_us() -> dict | None:
    import yfinance as yf

    tickers = ["SPY"] + list(US_SECTORS) + [t for _, ts in US_SECTORS.values() for t in ts]
    data = yf.download(tickers, period="1y", progress=False, auto_adjust=True, group_by="ticker", threads=True)

    def series(t):
        try:
            df = data[t].dropna()
        except KeyError:
            return None
        return df if len(df) >= 200 else None

    spy = series("SPY")
    if spy is None:
        log("⚠️ 抓不到 SPY，略過美股")
        return None
    spy_20 = spy["Close"].iloc[-1] / spy["Close"].iloc[-21] - 1

    sectors = []
    for etf, (label, members) in US_SECTORS.items():
        df = series(etf)
        if df is not None:
            sectors.append({"etf": etf, "label": label, "members": members,
                            "rel_20d": float(df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1 - spy_20)})
    sectors.sort(key=lambda s: -s["rel_20d"])

    for rank, sec in enumerate(sectors[:3], 1):
        rows = []
        for t in sec["members"]:
            df = series(t)
            if df is None:
                continue
            c = df["Close"]
            cmf = _cmf(df)
            row = {"ticker": t, "df": df, "close": float(c.iloc[-1]), "cmf": cmf,
                   "vol_ratio": float(df["Volume"].tail(5).mean() / df["Volume"].tail(50).mean()),
                   "ret_20d": float(c.iloc[-1] / c.iloc[-21] - 1), "ma50": float(c.tail(50).mean()), "ma200": float(c.tail(200).mean()),
                   "high_52w": float(c.max())}
            if row["close"] > row["ma50"] and cmf is not None and cmf > 0:
                rows.append(row)
        if not rows:
            continue
        for key in ("cmf", "vol_ratio", "ret_20d"):
            for i, r in enumerate(sorted(rows, key=lambda r: -r[key])):
                r["score"] = r.get("score", 0) + i
        best = min(rows, key=lambda r: r["score"])
        info = {}
        try:
            info = yf.Ticker(best["ticker"]).info or {}
        except Exception as exc:  # noqa: BLE001 — 基本資料拿不到不影響選股
            log(f"⚠️ {best['ticker']} 基本資料讀取失敗：{exc}")
        df = best["df"]
        return {
            "market": "美股", "code": best["ticker"], "name": info.get("shortName") or best["ticker"],
            "industry": f"{sec['label']}（{sec['etf']}）", "data_date": df.index[-1].date().isoformat(),
            "price": round(best["close"], 2), "spark": [round(float(x), 2) for x in df["Close"].tail(60)],
            "metrics": {
                "sector_rank": rank, "sector_rel_20d_pct": round(sec["rel_20d"] * 100, 1),
                "cmf_20": round(best["cmf"], 3), "vol_ratio_5_50": round(best["vol_ratio"], 2),
                "ret_20d_pct": round(best["ret_20d"] * 100, 1), "above_ma50": True, "above_ma200": best["close"] > best["ma200"],
                "from_52w_high_pct": round((best["close"] / best["high_52w"] - 1) * 100, 1),
                "pe": round(info["trailingPE"], 1) if info.get("trailingPE") else None,
                "forward_pe": round(info["forwardPE"], 1) if info.get("forwardPE") else None,
            },
            "top_sectors": [{"label": s["label"], "etf": s["etf"], "rel_20d_pct": round(s["rel_20d"] * 100, 1)} for s in sectors[:5]],
        }
    log("⚠️ 前三強類股都沒有符合條件的個股")
    return None


# ---------- 新聞與角色觀點 ----------

def related_news(pick: dict, limit: int = 3) -> list[dict]:
    items = []
    for cat in ("tw_stock", "headline", "wd_stock"):
        try:
            xml = requests.get(CNYES_RSS.format(cat), headers={"User-Agent": UA}, timeout=20).text
        except requests.RequestException:
            continue
        for block in re.findall(r"<item>(.*?)</item>", xml, flags=re.S):
            title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"<title>(.*?)</title>", block, re.S) or [None, ""])[1])).strip()
            link = (re.search(r"<link>(.*?)</link>", block) or [None, ""])[1].strip()
            kw = (re.search(r"<media:keywords>(.*?)</media:keywords>", block, re.S) or [None, ""])[1]
            hay = title + kw
            hit = (pick["market"] == "台股" and (pick["code"] in hay or pick["name"] in hay)) or \
                  (pick["market"] == "美股" and f"{pick['code']}-US" in hay)
            if hit and link not in {i["url"] for i in items}:
                items.append({"title": title, "url": link})
        time.sleep(2)
    return items[:limit]


PROMPT = """你是一個財經網站的研究小組，今天用固定規則篩出一檔「觀察標的」：{name}（{code}，{market}，{industry}）。
請用段永平、巴菲特、芒格、李錄四位投資人的「投資框架」各寫一段 50～80 字的觀點。
這是 AI 依他們公開的投資理念做的模擬，不代表本人意見；這是研究素材，不是投資建議。

為什麼今天篩到它（規則）：{rule}

可以使用的數字（只能用這些數字，不可以自己編造其他數字或事件）：
{metrics}

近期相關新聞標題（可能為空；只能引用標題，不可推測內文）：
{news}

四位投資人（分析重點／說話風格）：
{personas}

規則：
- 用各自的說話風格寫，可以用第一人稱「我會先看…」，但不可以假裝自己真的買了、持有或賣了這檔股票，也不可以編造他們說過的名言。
- 他們都是長期價值投資者，「法人資金流」「股價動能」不是他們買股票的理由，最多只是讓他們注意到這家公司；立場必須由各自的分析重點決定：
  段永平看商業模式與產品、巴菲特看現金流與估值（本益比很高、又沒有現金流資料時，他不會偏多）、芒格看會怎麼失敗、李錄看十年後的確定性與管理層。
- 數字的意思照括號裡的說明，例如「月營收年增率」是跟去年同月比，不是月增。
- 每個人要給一個立場：「偏多」「中性」「保留」其中之一；芒格必須寫出至少一個具體的失敗情境或風險。
- 絕對不可以出現：目標價、加碼、減碼、停損、停利、進場、出場、建議買賣、逢低買、值得買、保證、必漲。不要叫讀者做任何交易，只描述數字與觀點。
- 用繁體中文，口吻像研究筆記，具體引用上面的數字，照括號裡的解讀方式理解數字，不要寫出英文欄位名稱。

只輸出 JSON，格式：
{{"summary": "一句話（30 字內）說明今天為什麼注意到它", "views": [{{"role": "duan", "stance": "中性", "text": "..."}}, ...四個，role 依序為 duan、buffett、munger、lilu...], "watch": ["接下來要追蹤的事（2～3 點，每點 25 字內）"]}}"""

RULES_TEXT = {
    "台股": "最近 5 個交易日外資加投信淨買超金額，該產業排名前三、個股在產業中最高，5 天中至少 3 天買超，股價站上 20 日均線。",
    "美股": "所屬類股 ETF 近 20 日相對 SPY 最強（前三），個股在類股中資金流（CMF）、量能比、20 日動能綜合排名最前，且股價在 50 日均線之上。",
}


def call_groq(prompt: str) -> str:
    for attempt in range(4):
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                          json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}],
                                "max_completion_tokens": 2500, "reasoning_effort": "low",
                                "response_format": {"type": "json_object"}}, timeout=120)
        if r.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    raise RuntimeError("Groq 一直回 429")


def has_banned(text: str) -> bool:
    return any(w in text for w in BANNED_WORDS)


def clean(text: str) -> str:
    """最後一道保險：整個子句含交易用語就拿掉，而不是在句子中間留下記號。"""
    if not has_banned(text):
        return text.strip()
    parts = re.split(r"(?<=[，。；！？])", text)
    kept = "".join(p for p in parts if not has_banned(p)).rstrip("，；")
    return (kept + ("。" if kept and not kept.endswith(("。", "！", "？")) else "")).strip()


def persona_views(pick: dict) -> dict | None:
    if not GROQ_API_KEY:
        return None
    prompt = PROMPT.format(
        name=pick["name"], code=pick["code"], market=pick["market"], industry=pick["industry"], rule=RULES_TEXT[pick["market"]],
        metrics=describe_metrics(pick["metrics"]),
        news="\n".join(f"- {n['title']}" for n in pick["news"]) or "（無）",
        personas="\n".join(f"- {key}｜{name}｜{focus}｜風格：{voice}" for key, name, focus, voice in PERSONAS))
    for attempt in range(3):
        try:
            out = json.loads(call_groq(prompt))
        except (json.JSONDecodeError, KeyError, RuntimeError, requests.RequestException) as exc:
            log(f"⚠️ 角色觀點產生失敗：{exc}")
            continue
        views = {v.get("role"): v for v in out.get("views", [])}
        if attempt < 2 and has_banned(json.dumps(out, ensure_ascii=False)):
            log("⚠️ 角色觀點出現交易用語，重新產生")
            continue
        if all(k in views for k, *_ in PERSONAS):
            return {
                "summary": clean(out.get("summary", "")),
                "views": [{"role": k, "name": name, "focus": focus,
                           "stance": views[k].get("stance") if views[k].get("stance") in ("偏多", "中性", "保留") else "中性",
                           "text": clean(views[k].get("text", ""))} for k, name, focus, _ in PERSONAS],
                "watch": [clean(w) for w in out.get("watch", [])][:3],
            }
    return None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today_file = OUT_DIR / f"{datetime.now(TAIPEI).date().isoformat()}.json"
    if today_file.exists() and os.environ.get("PICKS_FORCE") != "1":
        print(f"今天的觀察標的已經產生過（{today_file.name}），同一天內不重新產生，避免內容一直變")
        try:
            refresh_flows()  # 觀察標的不變，但供應鏈地圖用的法人資料要更新
        except Exception as exc:  # noqa: BLE001
            log(f"⚠️ 法人資料更新失敗：{exc}")
        return 0
    picks = []
    for fn in (pick_tw, pick_us):
        try:
            p = fn()
        except Exception as exc:  # noqa: BLE001 — 一邊失敗不影響另一邊
            log(f"⚠️ {fn.__name__} 失敗：{type(exc).__name__}: {exc}")
            p = None
        if p:
            p["news"] = related_news(p)
            p["views"] = persona_views(p)
            p["rule"] = RULES_TEXT[p["market"]]
            picks.append(p)
    if not picks:
        log("⚠️ 今天沒有產生任何觀察標的")
        return 0
    today = datetime.now(TAIPEI).date().isoformat()
    (OUT_DIR / f"{today}.json").write_text(
        json.dumps({"date": today, "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"), "picks": picks},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 今日觀察：{'、'.join(p['market'] + ' ' + p['code'] for p in picks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
