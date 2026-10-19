"""
AI 投資顧問的每日資料（只放在密碼保護的 /portfolio/ 底下）。

設計參考站長提供的「AI 台股投資決策系統」：籌碼 × 財報 × 輿情，再讓「風控派」與「回測派」辯論。
這支程式只負責把「真實、可查證的數字」算好；AI 回答時只能引用這裡的數字。

每一檔的資料：
- 風控（陣營 A）：近一年報酬、年化波動、最大回撤（1 年／3 年）、單日 VaR 95%、最差 20 日、
  對 0050 的 Beta、大盤近 3 年最慘 20 天的同期表現（壓力測試）、融資餘額與使用率
- 回測（陣營 B）：近 3 年「站上 60 日線且 20 日動能為正才持有」的規則回測（扣手續費與證交稅），
  跟買進持有比較：年化報酬、最大回撤、交易次數、勝率、每筆平均報酬；夏普比率
- 多因子：月營收年增、本益比（越低越好）、投信 5 日買超，在全市場的百分位
- 財報：月營收（證交所／櫃買 OpenAPI）、毛利率／營益率／淨利率（最新一季）、本益比、股價淨值比、殖利率、ROE≈PB÷PE
- 籌碼：外資、投信近 5 日買賣超（上市，picks.py 存的證交所 T86）；上櫃只有當日（櫃買 OpenAPI）
- 輿情：PTT 股板最近約 300 篇標題的提及次數、[標的] 文多空篇數（Mobile01 的 robots 拒絕抓取，不使用）
- 供應鏈：supply_map.py 已核對出處的關係
- 每週研究：investment-team 最近一次篩選的通過／未通過項目

涵蓋範圍：持股、供應鏈地圖、今日觀察、每週研究候選、成交值前 250 名、顧問頁問過但還沒涵蓋的股票
（data/advisor/watch.json，由 workflow 從 D1 匯出）。其他股票仍有財報與估值，只是沒有價格風險與回測。

輸出 data/advisor/stocks.json，build.py 複製到 site/portfolio/advisor/stocks.json。
"""

import html
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "advisor" / "stocks.json"
WATCH = ROOT / "data" / "advisor" / "watch.json"
FLOWS = ROOT / "data" / "flows" / "latest.json"
PICKS_DIR = ROOT / "data" / "picks"
REPORT_DIR = Path(os.environ.get("SOURCES_DIR", ROOT / "sources")) / "investment-team" / "data" / "reports"
TAIPEI = timezone(timedelta(hours=8))
UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)"
TWSE = "https://openapi.twse.com.tw/v1"
TPEX = "https://www.tpex.org.tw/openapi/v1"
TOP_N = 250
FEE, TAX = 0.001425, 0.003
RISK_FREE = 0.015  # 台灣一年期定存約 1.5%，算夏普比率用
PTT_PAGES = 15


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def get_json(url: str):
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == 2:
                log(f"⚠️ {url} 讀取失敗：{exc}")
                return []
            time.sleep(5)


def num(x):
    if x is None:
        return None
    s = str(x).replace(",", "").strip()
    if s in ("", "-", "--", "N/A"):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def r2(x, d=2):
    return None if x is None or not math.isfinite(x) else round(x, d)


def roc_month(s: str) -> str | None:
    # 民國年月 11508 → 2026-08
    return f"{int(s[:-2]) + 1911}-{s[-2:]}" if s and s.isdigit() and len(s) >= 4 else None


def roc_day(s: str) -> str | None:
    return f"{int(s[:3]) + 1911}-{s[3:5]}-{s[5:7]}" if re.fullmatch(r"\d{7}", s or "") else None


# ---------- 全市場資料（便宜，一次一個請求） ----------

# 證交所／櫃買的產業別代碼
INDUSTRY_CODES = {
    "01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維", "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷",
    "09": "造紙工業", "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業", "14": "建材營造業", "15": "航運業", "16": "觀光餐旅",
    "17": "金融保險業", "18": "貿易百貨業", "19": "綜合", "20": "其他業", "21": "化學工業", "22": "生技醫療業", "23": "油電燃氣業",
    "24": "半導體業", "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業", "28": "電子零組件業", "29": "電子通路業",
    "30": "資訊服務業", "31": "其他電子業", "32": "文化創意業", "33": "農業科技業", "34": "電子商務", "35": "綠能環保",
    "36": "數位雲端", "37": "運動休閒", "38": "居家生活",
}


def market_data() -> dict:
    stocks: dict[str, dict] = {}

    def base(code, name, market):
        return stocks.setdefault(code, {"code": code, "name": (name or "").replace("*", "").strip(), "market": market})

    for r in get_json(f"{TWSE}/exchangeReport/STOCK_DAY_ALL"):
        s = base(r["Code"], r["Name"], "上市")
        s["close"], s["trade_value"] = num(r["ClosingPrice"]), num(r["TradeValue"])
    for r in get_json(f"{TPEX}/tpex_mainboard_quotes"):
        s = base(r["SecuritiesCompanyCode"], r["CompanyName"], "上櫃")
        s["close"], s["trade_value"] = num(r["Close"]), num(r["TransactionAmount"])

    # 已發行股數 → 市值（選股機器人用來判斷產業龍頭）；產業別也從這裡補（金融股沒有月營收檔，原本會沒有產業）
    for url, key, field, ind in ((f"{TWSE}/opendata/t187ap03_L", "公司代號", "已發行普通股數或TDR原股發行股數", "產業別"),
                                 (f"{TPEX}/mopsfin_t187ap03_O", "SecuritiesCompanyCode", "IssueShares", "SecuritiesIndustryCode")):
        for r in get_json(url):
            s = stocks.get(r.get(key))
            n = num(r.get(field))
            if s and n and s.get("close"):
                s["mcap_yi"] = round(s["close"] * n / 1e8, 1)
            if s and not s.get("industry"):
                s["industry"] = INDUSTRY_CODES.get(str(r.get(ind) or "").strip().zfill(2))

    for url, key in ((f"{TWSE}/opendata/t187ap05_L", "公司代號"), (f"{TPEX}/mopsfin_t187ap05_O", "公司代號")):
        for r in get_json(url):
            s = stocks.get(r[key])
            if not s:
                continue
            s["industry"] = r.get("產業別")
            s["revenue"] = {
                "month": roc_month(r.get("資料年月", "")),
                "amount_k": num(r.get("營業收入-當月營收")),
                "yoy": r2(num(r.get("營業收入-去年同月增減(%)")), 1),
                "mom": r2(num(r.get("營業收入-上月比較增減(%)")), 1),
                "ytd_yoy": r2(num(r.get("累計營業收入-前期比較增減(%)")), 1),
            }

    for r in get_json(f"{TWSE}/opendata/t187ap17_L"):
        s = stocks.get(r["公司代號"])
        if s:
            s["margins"] = {"quarter": f'{int(r["年度"]) + 1911}Q{r["季別"]}',
                            "gross": num(r.get("毛利率(%)(營業毛利)/(營業收入)")),
                            "operating": num(r.get("營業利益率(%)(營業利益)/(營業收入)")),
                            "net": num(r.get("稅後純益率(%)(稅後純益)/(營業收入)"))}
    for r in get_json(f"{TPEX}/mopsfin_187ap17_O"):
        s = stocks.get(r["SecuritiesCompanyCode"])
        if s:
            s["margins"] = {"quarter": f'{int(r["Year"]) + 1911}Q{r["季別"]}', "gross": num(r.get("毛利率")),
                            "operating": num(r.get("營業利益率")), "net": num(r.get("稅後純益率"))}

    def valuation(s, pe, pb, dy):
        s["valuation"] = {"pe": pe, "pb": pb, "yield": dy,
                          # ROE ≈ 淨值比 ÷ 本益比（近四季），本益比空白代表虧損
                          "roe_est": r2(pb / pe * 100, 1) if pe and pb and pe > 0 else None}

    for r in get_json(f"{TWSE}/exchangeReport/BWIBBU_ALL"):
        if r["Code"] in stocks:
            valuation(stocks[r["Code"]], num(r["PEratio"]), num(r["PBratio"]), num(r["DividendYield"]))
    for r in get_json(f"{TPEX}/tpex_mainboard_peratio_analysis"):
        if r["SecuritiesCompanyCode"] in stocks:
            valuation(stocks[r["SecuritiesCompanyCode"]], num(r["PriceEarningRatio"]), num(r["PriceBookRatio"]), num(r["YieldRatio"]))

    # 融資：今日餘額、單日增減、使用率（張）
    for r in get_json(f"{TWSE}/exchangeReport/MI_MARGN"):
        s = stocks.get(r["股票代號"])
        bal, prev, cap = num(r["融資今日餘額"]), num(r["融資前日餘額"]), num(r["融資限額"])
        if s and bal is not None:
            s["margin"] = {"balance": bal, "change": bal - (prev or 0), "usage": r2(bal / cap * 100, 1) if cap else None}
    for r in get_json(f"{TPEX}/tpex_mainboard_margin_balance"):
        s = stocks.get(r["SecuritiesCompanyCode"])
        bal, prev = num(r["MarginPurchaseBalance"]), num(r["MarginPurchaseBalancePreviousDay"])
        if s and bal is not None:
            s["margin"] = {"balance": bal, "change": bal - (prev or 0), "usage": num(r["MarginPurchaseUtilizationRate"])}

    # 籌碼：上市用 picks.py 存的 5 日 T86（張）；上櫃用櫃買當日資料（股 → 張）
    flows = json.loads(FLOWS.read_text(encoding="utf-8")) if FLOWS.exists() else {"codes": {}}
    for code, f in flows.get("codes", {}).items():
        if code in stocks:
            stocks[code]["flows"] = {"days": flows.get("days", 5), "date": flows.get("date"), **f}
    for r in get_json(f"{TPEX}/tpex_3insti_daily_trading"):
        s = stocks.get(r["SecuritiesCompanyCode"])
        if not s or "flows" in s:
            continue
        vals = {k.strip(): v for k, v in r.items()}
        foreign = num(vals.get("Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference"))
        trust = num(vals.get("SecuritiesInvestmentTrustCompanies-Difference"))
        s["flows"] = {"days": 1, "date": roc_day(r.get("Date", "")), "foreign_lots": round((foreign or 0) / 1000),
                      "trust_lots": round((trust or 0) / 1000), "buy_days": None}
    return stocks


def add_percentiles(stocks: dict) -> None:
    """多因子（回測派常用）：營收年增、本益比（低者佳）、投信買超，在全市場普通股的百分位。"""
    common = [s for s in stocks.values() if re.fullmatch(r"\d{4}", s["code"])]

    def rank(values: dict, higher_better=True):
        items = sorted(values.items(), key=lambda kv: kv[1], reverse=higher_better)
        n = len(items)
        return {code: round((n - i) / n * 100) for i, (code, _) in enumerate(items)} if n else {}

    rev = rank({s["code"]: s["revenue"]["yoy"] for s in common if (s.get("revenue") or {}).get("yoy") is not None})
    pe = rank({s["code"]: s["valuation"]["pe"] for s in common if ((s.get("valuation") or {}).get("pe") or 0) > 0}, higher_better=False)
    # 上櫃只有當日資料，跟上市的 5 日加總不能放在一起排
    trust = rank({s["code"]: s["flows"]["trust_lots"] for s in common if (s.get("flows") or {}).get("days") == 5})
    for s in common:
        f = {"revenue_yoy": rev.get(s["code"]), "low_pe": pe.get(s["code"]), "trust_buy": trust.get(s["code"])}
        got = [v for v in f.values() if v is not None]
        s["factors"] = {**f, "composite": round(sum(got) / len(got)) if len(got) >= 2 else None}


# ---------- 價格：風控與回測 ----------

def risk_metrics(close, bench) -> dict:
    import pandas as pd

    rets = close.pct_change().dropna()
    y1 = close.tail(252)
    r1 = rets.tail(251)
    out = {
        "price": r2(float(close.iloc[-1])), "date": close.index[-1].date().isoformat(),
        "ret_1y": r2(float(y1.iloc[-1] / y1.iloc[0] - 1) * 100, 1),
        "vol_1y": r2(float(r1.std() * math.sqrt(252)) * 100, 1),
        "mdd_1y": r2(float((y1 / y1.cummax() - 1).min()) * 100, 1),
        "mdd_3y": r2(float((close / close.cummax() - 1).min()) * 100, 1),
        "var95_1d": r2(float(r1.quantile(0.05)) * 100, 2),
        "worst_20d": r2(float((close / close.shift(20) - 1).min()) * 100, 1),
        "from_52w_high": r2(float(close.iloc[-1] / y1.max() - 1) * 100, 1),
        "chg_1d": r2(float(close.iloc[-1] / close.iloc[-2] - 1) * 100, 2),
        "chg_5d": r2(float(close.iloc[-1] / close.iloc[-6] - 1) * 100, 1) if len(close) > 6 else None,
        "chg_20d": r2(float(close.iloc[-1] / close.iloc[-21] - 1) * 100, 1) if len(close) > 21 else None,
        "above_ma60": bool(close.iloc[-1] > close.tail(60).mean()) if len(close) >= 60 else None,
        "above_ma120": bool(close.iloc[-1] > close.tail(120).mean()) if len(close) >= 120 else None,
        "years": r2(len(close) / 252, 1),
        "spark": [r2(float(x)) for x in close.tail(120).iloc[::2]],
    }
    vol = r1.std() * math.sqrt(252)
    ann = (1 + r1.mean()) ** 252 - 1
    out["sharpe_1y"] = r2(float((ann - RISK_FREE) / vol), 2) if vol > 0 else None
    if bench is not None:
        both = pd.concat([r1, bench.pct_change()], axis=1, join="inner").dropna()
        if len(both) > 60 and both.iloc[:, 1].var() > 0:
            out["beta"] = r2(float(both.iloc[:, 0].cov(both.iloc[:, 1]) / both.iloc[:, 1].var()), 2)
        # 壓力測試：0050 近 3 年最慘的 20 個交易日，這檔同期跌多少
        b20 = bench / bench.shift(20) - 1
        end = b20.idxmin()
        if not math.isnan(b20.min()) and end in close.index:
            start = bench.index[bench.index.get_loc(end) - 20]
            if start in close.index:
                out["stress"] = {"from": start.date().isoformat(), "to": end.date().isoformat(),
                                 "market": r2(float(b20.min()) * 100, 1),
                                 "stock": r2(float(close[end] / close[start] - 1) * 100, 1)}
    return out


def backtest(close) -> dict | None:
    """規則：收盤站上 60 日線且近 20 日報酬為正 → 隔天開始持有；任一條件不成立 → 隔天出場。
    每次買進扣 0.1425%、賣出扣 0.1425% + 0.3%。只用近 3 年資料（樣本內），不代表未來。"""
    if len(close) < 200:
        return None
    ma60 = close.rolling(60).mean()
    mom20 = close / close.shift(20) - 1
    signal = ((close > ma60) & (mom20 > 0)).shift(1, fill_value=False)
    rets = close.pct_change().fillna(0)
    valid = ma60.notna()
    signal, rets, px = signal[valid], rets[valid], close[valid]

    equity, eq_curve, trades, entry, holding = 1.0, [], [], None, False
    for day, on in signal.items():
        if on and not holding:
            equity *= 1 - FEE
            entry, holding = px[day], True
        elif not on and holding:
            equity *= 1 - FEE - TAX
            trades.append(px[day] / entry * (1 - FEE) * (1 - FEE - TAX) - 1)
            holding = False
        if holding and day != signal.index[0]:
            equity *= 1 + rets[day]
        eq_curve.append(equity)
    if holding:
        trades.append(px.iloc[-1] / entry * (1 - FEE) * (1 - FEE - TAX) - 1)

    years = len(px) / 252
    import pandas as pd
    eq = pd.Series(eq_curve, index=px.index)
    bh = px / px.iloc[0]
    cagr = lambda end: (end ** (1 / years) - 1) * 100 if end > 0 else -100  # noqa: E731
    return {
        "rule": "站上 60 日線且 20 日動能為正才持有",
        "period": f"{px.index[0].date().isoformat()} ~ {px.index[-1].date().isoformat()}",
        "strategy_cagr": r2(cagr(eq.iloc[-1]), 1), "strategy_mdd": r2(float((eq / eq.cummax() - 1).min()) * 100, 1),
        "hold_cagr": r2(cagr(bh.iloc[-1]), 1), "hold_mdd": r2(float((bh / bh.cummax() - 1).min()) * 100, 1),
        "trades": len(trades),
        "win_rate": r2(sum(t > 0 for t in trades) / len(trades) * 100, 0) if trades else None,
        "avg_trade": r2(sum(trades) / len(trades) * 100, 1) if trades else None,
        "in_market": r2(float(signal.mean()) * 100, 0),
        "holding_now": bool(signal.iloc[-1]) if len(signal) else None,
    }


def price_data(codes: list[str], stocks: dict) -> dict:
    import yfinance as yf

    def yft(code):
        return f"{code}.TWO" if stocks.get(code, {}).get("market") == "上櫃" else f"{code}.TW"

    tickers = {yft(c): c for c in codes}
    closes = {}
    pending = list(tickers)
    for attempt in range(3):
        failed = []
        for i in range(0, len(pending), 60):
            chunk = pending[i:i + 60]
            data = yf.download(chunk, period="3y", progress=False, auto_adjust=True, group_by="ticker", threads=True)
            for t in chunk:
                try:
                    c = data[t]["Close"].dropna()
                except KeyError:
                    c = None
                if c is not None and len(c) > 60:
                    closes[t] = c
                else:
                    failed.append(t)
            time.sleep(4)
        if not failed:
            break
        log(f"⚠️ 第 {attempt + 1} 輪有 {len(failed)} 檔沒抓到：{' '.join(failed[:10])}")
        pending = failed
        if attempt < 2:
            time.sleep(30)
    bench = closes.get("0050.TW")
    out = {}
    for t, c in closes.items():
        code = tickers[t]
        try:
            out[code] = {"risk": risk_metrics(c, bench if code != "0050" else None), "backtest": backtest(c)}
        except Exception as exc:  # 單一檔資料異常不影響其他
            log(f"⚠️ {code} 計算失敗：{exc}")
    return out


# ---------- 輿情：PTT 股板 ----------

def ptt_titles() -> list[dict]:
    """PTT 股板最新幾頁的標題（www.ptt.cc 沒有 robots.txt 限制；每頁間隔 1 秒）。"""
    titles, url = [], "https://www.ptt.cc/bbs/Stock/index.html"
    for _ in range(PTT_PAGES):
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        except requests.RequestException as exc:
            log(f"⚠️ PTT 讀取失敗：{exc}")
            break
        if resp.status_code != 200:
            log(f"⚠️ PTT 回 {resp.status_code}（雲端主機的 IP 常被擋），改由顧問頁即時抓取")
            break
        page = resp.text
        for href, title in re.findall(r'<div class="title">\s*<a href="([^"]+)">([^<]+)</a>', page):
            titles.append({"title": html.unescape(title).strip(), "url": "https://www.ptt.cc" + href})
        prev = re.search(r'<a class="btn wide" href="([^"]+)">&lsaquo; 上頁</a>', page)
        if not prev:
            break
        url = "https://www.ptt.cc" + prev.group(1)
        time.sleep(1)
    return titles


def ptt_for(code: str, name: str, titles: list[dict]) -> dict:
    short = name.replace("-KY", "").replace("*", "")
    seen, hits = set(), []
    for t in titles:
        key = re.sub(r"^(Re|Fw):\s*", "", t["title"])
        if (code in key or (len(short) >= 2 and short in key)) and key not in seen:
            seen.add(key)
            hits.append({**t, "title": key})
    bull = bear = 0
    for t in hits:
        if t["title"].startswith("[標的]"):
            tail = t["title"][-3:]
            bull += "多" in tail
            bear += "空" in tail
    return {"mentions": len(hits), "target_bull": bull, "target_bear": bear,
            "titles": [t["title"] for t in hits[:5]], "sample": len(titles)}


# ---------- 範圍 ----------

def holdings_codes() -> list[str]:
    try:
        import portfolio
        return [t["code"] for t in portfolio.load_notion()["tickers"] if t["shares"] and t["code"]]
    except Exception as exc:
        log(f"⚠️ 讀不到持股（{exc}），範圍不含持股")
        return []


def weekly_screen() -> tuple[str | None, dict]:
    if not REPORT_DIR.is_dir():
        return None, {}
    for f in sorted(REPORT_DIR.glob("*.json"), reverse=True):
        d = json.loads(f.read_text(encoding="utf-8"))
        s = d.get("screen") if isinstance(d, dict) else None
        if s and (s.get("value") or s.get("growth")):
            out = {}
            for style in ("value", "growth"):
                for c in s.get(style) or []:
                    checks = c.get("checks") or []
                    out[c["code"]] = {"style": "價值" if style == "value" else "成長",
                                      "passed": sum(1 for x in checks if x.get("passed")), "total": len(checks),
                                      "failed": [x["detail"] for x in checks if not x.get("passed")][:3],
                                      "highlights": [x["detail"] for x in checks if x.get("passed")][:4]}
            return f.stem, out
    return None, {}


def universe(stocks: dict, held: list[str], weekly: dict, with_watch: bool = True) -> list[str]:
    from supply_map import ALL_TW

    picks = []
    files = sorted(PICKS_DIR.glob("*.json"))[-5:] if PICKS_DIR.is_dir() else []
    for f in files:
        picks += [p["code"] for p in json.loads(f.read_text(encoding="utf-8")).get("picks", []) if p.get("market") == "台股"]
    watch = json.loads(WATCH.read_text(encoding="utf-8")) if WATCH.exists() and with_watch else []
    top = sorted((s for s in stocks.values() if s.get("trade_value") and re.fullmatch(r"\d{4}", s["code"])),
                 key=lambda s: -s["trade_value"])[:TOP_N]
    codes = ["0050", "0056", "006208", "00878", *held, *ALL_TW, *picks, *weekly, *watch, *(s["code"] for s in top)]
    seen = set()
    return [c for c in codes if c in stocks and not (c in seen or seen.add(c))]


def main() -> int:
    from supply_map import LEADERS, SOURCES, TW_MAP, TW_PEERS

    stocks = market_data()
    if len(stocks) < 1000:
        log(f"❌ 全市場資料只有 {len(stocks)} 檔，證交所／櫃買可能暫時掛掉")
        return 1
    add_percentiles(stocks)
    held = holdings_codes()
    weekly_date, weekly = weekly_screen()
    codes = universe(stocks, held, weekly)
    log(f"價格範圍 {len(codes)} 檔（持股 {len(held)}、每週研究 {len(weekly)}）")
    prices = price_data(codes, stocks)
    titles = ptt_titles()

    for code in codes:
        s = stocks[code]
        s.update(prices.get(code, {}))
        s["ptt"] = ptt_for(code, s["name"], titles) if titles else None
        if code in weekly:
            s["weekly"] = {"date": weekly_date, **weekly[code]}
        links = TW_MAP.get(code, {}).get("links", {})
        if links:
            s["supply"] = [{"leader": LEADERS[ld][0], "relation": rel, "note": note,
                            "source": dict(zip(("publisher", "date", "title", "url"), SOURCES[src][:4]))}
                           for ld, (rel, note, src) in links.items() if rel != "同業" and src in SOURCES]
        if TW_PEERS.get(code):
            s["peers"] = [{"code": p["code"], "name": p["name"], "group": p["group"]} for p in TW_PEERS[code]][:6]

    out = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
        "price_codes": sorted(prices),
        # 不靠站長持股與顧問頁提問就會在範圍內的股票；訪客版機器人只對這些顯示風控與回測，避免從範圍反推持股
        "public_codes": sorted(set(universe(stocks, [], weekly, with_watch=False)) & set(prices)),
        "ptt_sample": len(titles), "weekly_date": weekly_date,
        "stocks": {c: {k: v for k, v in s.items() if k != "trade_value"} for c, s in stocks.items()
                   if re.fullmatch(r"\d{4}|00\d{2,4}[A-Z]?", c)},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"✅ AI 顧問資料：全市場 {len(out['stocks'])} 檔、有風控與回測 {len(prices)} 檔、PTT {len(titles)} 篇、"
        f"{OUT.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
