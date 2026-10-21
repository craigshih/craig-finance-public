"""
「市場」頁的每日資料（參考 AI 產業地圖 App 的每日焦點／熱力圖／處置股預警／行事曆，全部改用公開資料自己算）。

- 指數看板：yfinance 半年日 K（台股加權、台積電 ADR、費半、S&P 500、那斯達克、日經、韓股、VIX、原油、美元指數、美元兌台幣）
- 產業熱力圖：證交所＋櫃買當日收盤，產業別取自月營收資料；面積＝成交值，顏色＝成交值加權漲跌
- 三大法人買賣超（證交所 BFI82U）與融資餘額（證交所信用交易統計），每天累積在 data/market/history.json
- 強勢股：AI 顧問資料（成交值前 250 名等約 300 檔）的 1／5／20 日漲幅
- 大戶加碼：集保戶股權分散表（每週），400 張以上大戶持股比例的週變化；每週存一份 data/market/tdcc/{date}.json
- 處置／注意股：證交所與櫃買公告（處置中、當日注意、注意次數可能達處置標準）
- 除權息行事曆：證交所與櫃買的除權除息預告表

輸出 data/market/latest.json，build.py 讀取產生 /market/。
"""

import csv
import io
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "data" / "market"
HISTORY = OUT_DIR / "history.json"
TDCC_DIR = OUT_DIR / "tdcc"
ADVISOR = ROOT / "data" / "advisor" / "stocks.json"
TAIPEI = timezone(timedelta(hours=8))
UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)"
TWSE_OPEN = "https://openapi.twse.com.tw/v1"
TPEX = "https://www.tpex.org.tw/openapi/v1"

INDICES = [
    ("^TWII", "台股加權", "台"), ("TSM", "台積電 ADR", "美"), ("^SOX", "費城半導體", "美"), ("^GSPC", "S&P 500", "美"),
    ("^IXIC", "那斯達克", "美"), ("^N225", "日經 225", "日"), ("^KS11", "韓國綜合", "韓"), ("^STOXX50E", "歐洲 STOXX 50", "歐"), ("^VIX", "VIX 恐慌指數", "美"),
    ("CL=F", "WTI 原油", "商品"), ("DX-Y.NYB", "美元指數", "匯率"), ("TWD=X", "美元兌台幣", "匯率"),
    ("JPYTWD=X", "100 日圓兌台幣", "匯率"), ("EURTWD=X", "歐元兌台幣", "匯率"),
]
SCALE = {"JPYTWD=X": 100}  # 1 日圓約 0.2 台幣，取兩位小數看不出變化，改用 100 日圓計價（live.js 同步）
HISTORY_DAYS = 60


def clean(name: str) -> str:
    return (name or "").replace("*", "").strip()  # 官方股名的「*」（面額非 10 元）不顯示


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def get_json(url: str, params: dict | None = None):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=40)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == 2:
                log(f"⚠️ {url} 讀取失敗：{exc}")
                return None
            time.sleep(4)


def num(x):
    try:
        v = float(str(x).replace(",", "").replace("+", "").strip())
    except (TypeError, ValueError):
        return None
    return v


def roc(s: str) -> str | None:
    s = (s or "").strip()
    if re.fullmatch(r"\d{7}", s):
        return f"{int(s[:3]) + 1911}-{s[3:5]}-{s[5:7]}"
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return None


# ---------- 指數看板 ----------

def indices() -> list[dict]:
    import yfinance as yf

    data = yf.download([t for t, *_ in INDICES], period="6mo", progress=False, auto_adjust=False, group_by="ticker", threads=True)
    out = []
    for ticker, name, region in INDICES:
        try:
            df = data[ticker].dropna(subset=["Close"]) * SCALE.get(ticker, 1)
        except KeyError:
            continue
        if len(df) < 2:
            log(f"⚠️ {name} 沒有資料")
            continue
        c = df["Close"]
        out.append({
            "ticker": ticker, "name": name, "region": region,
            "close": round(float(c.iloc[-1]), 2), "date": df.index[-1].date().isoformat(),
            "chg": round(float(c.iloc[-1] - c.iloc[-2]), 2), "chg_pct": round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
            "ohlc": [[d.date().isoformat(), *(round(float(r[k]), 2) for k in ("Open", "High", "Low", "Close"))]
                     for d, r in df.iterrows() if all(r[k] == r[k] for k in ("Open", "High", "Low", "Close"))],
        })
    return out


# ---------- 產業熱力圖 ----------

def quotes_and_industry() -> list[dict]:
    rows = []
    for r in get_json(f"{TWSE_OPEN}/exchangeReport/STOCK_DAY_ALL") or []:
        close, chg = num(r["ClosingPrice"]), num(r["Change"])
        rows.append({"code": r["Code"], "name": clean(r["Name"]), "market": "上市", "close": close, "chg": chg, "tv": num(r["TradeValue"])})
    for r in get_json(f"{TPEX}/tpex_mainboard_quotes") or []:
        close, chg = num(r["Close"]), num(r["Change"])
        rows.append({"code": r["SecuritiesCompanyCode"], "name": clean(r["CompanyName"]), "market": "上櫃", "close": close, "chg": chg,
                     "tv": num(r["TransactionAmount"])})
    industry = {}
    for url in (f"{TWSE_OPEN}/opendata/t187ap05_L", f"{TPEX}/mopsfin_t187ap05_O"):
        for r in get_json(url) or []:
            industry[r["公司代號"]] = r.get("產業別")
    out = []
    for q in rows:
        if not re.fullmatch(r"\d{4}", q["code"]) or not q["close"] or q["chg"] is None or not q["tv"]:
            continue
        prev = q["close"] - q["chg"]
        if prev <= 0:
            continue
        out.append({**q, "pct": round(q["chg"] / prev * 100, 2), "industry": industry.get(q["code"])})
    return out


def industry_heat(stocks: list[dict]) -> list[dict]:
    groups: dict[str, list] = {}
    for s in stocks:
        if s["industry"]:
            groups.setdefault(s["industry"], []).append(s)
    out = []
    for name, members in groups.items():
        tv = sum(m["tv"] for m in members)
        if tv <= 0:
            continue
        top = sorted(members, key=lambda m: -m["tv"])[:4]
        out.append({"name": name, "tv": tv, "pct": round(sum(m["pct"] * m["tv"] for m in members) / tv, 2),
                    "n": len(members), "up": sum(m["pct"] > 0 for m in members),
                    "top": [{"code": m["code"], "name": m["name"], "pct": m["pct"]} for m in top]})
    return sorted(out, key=lambda g: -g["tv"])


def theme_heat(stocks: list[dict]) -> list[dict]:
    """供應鏈地圖裡有出處的台股族群（CoWoS、散熱、PCB…），用同樣方式算。"""
    from supply_map import PEER_GROUPS

    by_code = {s["code"]: s for s in stocks}
    out = []
    for name, members, _ in PEER_GROUPS:
        ms = [by_code[c] for c, _ in members if c in by_code]
        tv = sum(m["tv"] for m in ms)
        if len(ms) < 2 or tv <= 0:
            continue
        out.append({"name": name, "tv": tv, "pct": round(sum(m["pct"] * m["tv"] for m in ms) / tv, 2), "n": len(ms),
                    "up": sum(m["pct"] > 0 for m in ms),
                    "top": [{"code": m["code"], "name": m["name"], "pct": m["pct"]} for m in sorted(ms, key=lambda m: -m["tv"])[:4]]})
    return sorted(out, key=lambda g: -g["tv"])


# ---------- 三大法人與融資（每天累積） ----------

def bfi82u(day: date | None = None) -> dict | None:
    params = {"response": "json"}
    if day:
        params["dayDate"] = day.strftime("%Y%m%d")
    d = get_json("https://www.twse.com.tw/rwd/zh/fund/BFI82U", params)
    if not d or d.get("stat") != "OK" or not d.get("data"):
        return None
    rows = {r[0]: num(r[3]) for r in d["data"]}
    yi = 1e8
    return {"date": roc(d.get("date", "")),
            "foreign": round((rows.get("外資及陸資(不含外資自營商)") or 0) / yi, 1),
            "trust": round((rows.get("投信") or 0) / yi, 1),
            "dealer": round(((rows.get("自營商(自行買賣)") or 0) + (rows.get("自營商(避險)") or 0)) / yi, 1),
            "total": round((rows.get("合計") or 0) / yi, 1)}


def margin_total(day: date | None = None) -> dict | None:
    params = {"response": "json", "selectType": "MS"}
    if day:
        params["date"] = day.strftime("%Y%m%d")
    d = get_json("https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN", params)
    if not d or d.get("stat") != "OK" or not d.get("tables"):
        return None
    for row in d["tables"][0].get("data", []):
        if row[0].startswith("融資金額"):
            today, prev = num(row[5]), num(row[4])
            return {"date": roc(d.get("date", "")), "margin_yi": round(today / 1e5, 1), "margin_chg_yi": round((today - prev) / 1e5, 1)}
    return None


def update_history() -> list[dict]:
    hist = {h["date"]: h for h in json.loads(HISTORY.read_text(encoding="utf-8"))} if HISTORY.exists() else {}
    days = [None]
    if len(hist) < 20:  # 第一次：往回補約 2 個月
        today = datetime.now(TAIPEI).date()
        days += [today - timedelta(days=i) for i in range(1, 90) if (today - timedelta(days=i)).weekday() < 5]
    for d in days:
        if d and d.isoformat() in hist:
            continue
        f = bfi82u(d)
        if f and f["date"]:
            m = margin_total(d)
            hist[f["date"]] = {**hist.get(f["date"], {}), **f, **({k: v for k, v in m.items() if k != "date"} if m else {})}
        if d:
            time.sleep(1.5)
        if len(hist) >= HISTORY_DAYS + 5:
            break
    out = sorted(hist.values(), key=lambda h: h["date"])[-HISTORY_DAYS:]
    HISTORY.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    return out


# ---------- 強勢股 ----------

def strong_stocks() -> dict:
    if not ADVISOR.exists():
        return {}
    data = json.loads(ADVISOR.read_text(encoding="utf-8"))
    rows = []
    for code in data.get("price_codes", []):
        s = data["stocks"].get(code) or {}
        r = s.get("risk") or {}
        if re.fullmatch(r"\d{4}", code) and r.get("chg_1d") is not None:
            rows.append({"code": code, "name": s["name"], "market": s["market"], "industry": s.get("industry"),
                         "price": r["price"], "d": r["chg_1d"], "w": r.get("chg_5d"), "m": r.get("chg_20d")})
    return {k: sorted((x for x in rows if x[k] is not None), key=lambda x: -x[k])[:12] for k in ("d", "w", "m")}


# ---------- 大戶加碼（集保，每週） ----------

def tdcc() -> dict:
    """400 張以上（分級 12～15）與 1000 張以上（分級 15）大戶的持股比例。"""
    try:
        text = requests.get("https://opendata.tdcc.com.tw/getOD.ashx?id=1-5", headers={"User-Agent": UA}, timeout=90).content.decode("utf-8-sig")
    except requests.RequestException as exc:
        log(f"⚠️ 集保資料讀取失敗：{exc}")
        return {}
    snap, day = {}, None
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 6 or not re.fullmatch(r"\d{4}", r[1].strip()):
            continue
        day = r[0]
        code, level, people, pct = r[1].strip(), int(r[2]), int(r[3]), float(r[5])
        s = snap.setdefault(code, [0.0, 0.0, 0])
        if 12 <= level <= 15:
            s[0] += pct
        if level == 15:
            s[1] += pct
        if level == 17:
            s[2] = people
    if not snap or not day:
        return {}
    TDCC_DIR.mkdir(parents=True, exist_ok=True)
    iso = roc(day)
    (TDCC_DIR / f"{iso}.json").write_text(json.dumps({c: [round(a, 2), round(b, 2), n] for c, (a, b, n) in snap.items()}), encoding="utf-8")
    files = sorted(TDCC_DIR.glob("*.json"))
    for old in files[:-6]:  # 留最近 6 週
        old.unlink()
    files = sorted(TDCC_DIR.glob("*.json"))
    if len(files) < 2:
        return {"date": iso, "prev": None, "rows": []}
    prev = json.loads(files[-2].read_text(encoding="utf-8"))
    return {"date": iso, "prev": files[-2].stem,
            "rows": [{"code": c, "big": round(v[0], 2), "big_chg": round(v[0] - prev[c][0], 2), "holders": v[2],
                      "holders_chg": v[2] - prev[c][2]}
                     for c, v in snap.items() if c in prev]}


# ---------- 處置／注意股 ----------

def warnings() -> list[dict]:
    out = []
    for r in get_json(f"{TWSE_OPEN}/announcement/punish") or []:
        if re.fullmatch(r"\d{4}", r.get("Code", "")):
            out.append({"code": r["Code"], "name": clean(r["Name"]), "market": "上市", "level": "處置中",
                        "period": r.get("DispositionPeriod"), "detail": f'{r.get("DispositionMeasures", "")}・{r.get("ReasonsOfDisposition", "")}'})
    for r in get_json(f"{TPEX}/tpex_disposal_information") or []:
        p = r.get("DispositionPeriod", "")
        a, _, b = p.partition("~")
        out.append({"code": r["SecuritiesCompanyCode"], "name": clean(r["CompanyName"]), "market": "上櫃", "level": "處置中",
                    "period": f"{roc(a) or a} ~ {roc(b) or b}", "detail": r.get("DispositionReasons", "")})
    for r in get_json(f"{TWSE_OPEN}/announcement/notetrans") or []:
        out.append({"code": r["Code"], "name": clean(r["Name"]), "market": "上市", "level": "可能處置",
                    "period": None, "detail": r.get("RecentlyMetAttentionSecuritiesCriteria", "")})
    for r in get_json(f"{TPEX}/tpex_trading_warning_note") or []:
        out.append({"code": r["SecuritiesCompanyCode"], "name": clean(r["CompanyName"]), "market": "上櫃", "level": "可能處置",
                    "period": None, "detail": r.get("AccumulationSituation", "")})
    for r in get_json(f"{TWSE_OPEN}/announcement/notice") or []:
        if re.fullmatch(r"\d{4}", r.get("Code", "")):
            out.append({"code": r["Code"], "name": clean(r["Name"]), "market": "上市", "level": "注意",
                        "period": None, "detail": r.get("TradingInfoForAttention", "")})
    for r in get_json(f"{TPEX}/tpex_trading_warning_information") or []:
        out.append({"code": r["SecuritiesCompanyCode"], "name": clean(r["CompanyName"]), "market": "上櫃", "level": "注意",
                    "period": None, "detail": r.get("TradingInformation", "")})
    rank = {"處置中": 0, "可能處置": 1, "注意": 2}
    seen, uniq = set(), []
    for w in sorted(out, key=lambda w: rank[w["level"]]):
        if (w["code"], w["level"]) not in seen:
            seen.add((w["code"], w["level"]))
            uniq.append(w)
    return uniq


# ---------- 除權息行事曆 ----------

def ex_dividends() -> list[dict]:
    today = datetime.now(TAIPEI).date().isoformat()
    out = []
    for r in get_json(f"{TWSE_OPEN}/exchangeReport/TWT48U_ALL") or []:
        out.append({"date": roc(r["Date"]), "code": r["Code"], "name": clean(r["Name"]), "market": "上市",
                    "type": "除" + r.get("Exdividend", ""), "cash": num(r.get("CashDividend")), "stock": num(r.get("StockDividendRatio"))})
    for r in get_json(f"{TPEX}/tpex_exright_prepost") or []:
        out.append({"date": roc(r["ExRrightsExDividendDate"]), "code": r["SecuritiesCompanyCode"], "name": clean(r["CompanyName"]), "market": "上櫃",
                    "type": r.get("ExRrightsExDividend", ""), "cash": num(r.get("CashDividend")), "stock": num(r.get("StockDividendRatio"))})
    return sorted((x for x in out if x["date"] and x["date"] >= today), key=lambda x: (x["date"], x["code"]))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stocks = quotes_and_industry()
    if len(stocks) < 800:
        log(f"❌ 當日報價只有 {len(stocks)} 檔")
        return 1
    names = {s["code"]: s["name"] for s in stocks}
    big = tdcc()
    big_rows = [r for r in big.get("rows", []) if r["code"] in names and r["holders"] >= 1000]
    for r in big_rows:
        r["name"] = names[r["code"]]
    out = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
        "quote_date": None,
        "indices": indices(),
        "industries": industry_heat(stocks),
        "themes": theme_heat(stocks),
        "breadth": {"up": sum(s["pct"] > 0 for s in stocks), "down": sum(s["pct"] < 0 for s in stocks),
                    "flat": sum(s["pct"] == 0 for s in stocks),
                    "limit_up": sum(s["pct"] >= 9.5 for s in stocks), "limit_down": sum(s["pct"] <= -9.5 for s in stocks)},
        "history": update_history(),
        "strong": strong_stocks(),
        "big_holders": {"date": big.get("date"), "prev": big.get("prev"),
                        "up": sorted(big_rows, key=lambda r: -r["big_chg"])[:12],
                        "down": sorted(big_rows, key=lambda r: r["big_chg"])[:12]},
        "warnings": warnings(),
        "ex_dividends": ex_dividends(),
    }
    (OUT_DIR / "latest.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"✅ 市場資料：指數 {len(out['indices'])}、產業 {len(out['industries'])}、題材 {len(out['themes'])}、"
        f"法人歷史 {len(out['history'])} 天、處置／注意 {len(out['warnings'])}、除權息 {len(out['ex_dividends'])}、"
        f"大戶 {big.get('date')}（對比 {big.get('prev')}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
