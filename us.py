"""
美股頁的資料：指數與利率、類股 ETF、重點個股（報價＋SEC 官方財報）、近期 SEC 申報、預估財報日。

  報價、走勢、市值：Yahoo Finance（yfinance）
  營收、淨利、現金流：SEC EDGAR companyfacts（公司向 SEC 申報的 XBRL 數字，非第三方估算）
  近期申報：SEC submissions（8-K 依 item 翻成中文，附原文連結）
  財報日：Yahoo 的預估日期，頁面會註明以公司公告為準

外國公司（TSM、ASML、ARM 等申報 20-F）沒有 us-gaap 數字，只顯示報價，不硬算。
輸出 data/us/latest.json。SEC 需要 SEC_USER_AGENT（同 whales.py）。
"""

import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from whales import SecBlocked, log, sec_get

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "us" / "latest.json"
WHALES = ROOT / "data" / "whales" / "latest.json"
SUPPLY = ROOT / "data" / "supply" / "latest.json"
TAIPEI = timezone(timedelta(hours=8))

INDICES = [("^GSPC", "S&P 500"), ("^IXIC", "那斯達克"), ("^DJI", "道瓊工業"), ("^SOX", "費城半導體"),
           ("^RUT", "羅素 2000"), ("^VIX", "VIX 恐慌指數"), ("^TNX", "美債 10 年殖利率"), ("DX-Y.NYB", "美元指數")]
SECTORS = [("XLK", "科技"), ("SMH", "半導體"), ("XLC", "通訊服務"), ("XLY", "非必需消費"), ("XLP", "必需消費"),
           ("XLF", "金融"), ("XLV", "醫療保健"), ("XLI", "工業"), ("XLE", "能源"), ("XLB", "原物料"),
           ("XLU", "公用事業"), ("XLRE", "不動產")]
GROUPS = {
    "科技巨頭": [("AAPL", "蘋果"), ("MSFT", "微軟"), ("NVDA", "輝達"), ("GOOGL", "Alphabet"), ("AMZN", "亞馬遜"),
             ("META", "Meta"), ("TSLA", "特斯拉"), ("AVGO", "博通")],
    "半導體": [("TSM", "台積電 ADR"), ("AMD", "超微"), ("MU", "美光"), ("QCOM", "高通"), ("INTC", "英特爾"), ("ARM", "安謀"),
            ("ASML", "艾司摩爾"), ("AMAT", "應用材料"), ("LRCX", "科林研發"), ("KLAC", "科磊"), ("MRVL", "邁威爾")],
    "AI 與軟體": [("ORCL", "甲骨文"), ("PLTR", "Palantir"), ("CRM", "Salesforce"), ("NOW", "ServiceNow"),
               ("ADBE", "Adobe"), ("NFLX", "Netflix"), ("SMCI", "美超微"), ("DELL", "戴爾")],
    "其他權值": [("JPM", "摩根大通"), ("BRK-B", "波克夏"), ("V", "Visa"), ("LLY", "禮來"), ("UNH", "聯合健康"),
             ("COST", "好市多"), ("WMT", "沃爾瑪"), ("XOM", "埃克森美孚")],
}
FILING_DAYS = 21
ITEMS_8K = {
    "1.01": "簽訂重大合約", "1.02": "終止重大合約", "1.05": "資安事件", "2.01": "完成收購或處分資產", "2.02": "公布財報",
    "2.03": "新增重大債務", "2.05": "重組／裁員費用", "2.06": "資產減損", "3.01": "上市資格通知", "3.02": "私募發行股票",
    "4.01": "更換會計師", "5.02": "董事或高層異動", "5.03": "修改章程", "5.07": "股東會投票結果", "7.01": "公平揭露（簡報、新聞稿）",
    "8.01": "其他重大事項",
}
TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "RevenuesNetOfInterestExpense", "Revenues",
                "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"],
    "net_income": ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets",
              "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets"],
}


# ---------------------------------------------------------------- 報價

def prices(tickers: list[str]) -> dict[str, dict]:
    import yfinance as yf
    data = yf.download(tickers, period="1y", progress=False, auto_adjust=False, group_by="ticker", threads=True)
    out = {}
    for t in tickers:
        try:
            s = data[t]["Close"].dropna()
        except KeyError:
            continue
        if len(s) < 25:
            continue
        c = [float(x) for x in s]
        last, dt = c[-1], s.index[-1].date()
        ytd_base = next((float(v) for d, v in zip(s.index, s) if d.year == dt.year), None)
        prev_year = [float(v) for d, v in zip(s.index, s) if d.year < dt.year]
        ytd_base = prev_year[-1] if prev_year else ytd_base
        r = lambda n: round((last / c[-1 - n] - 1) * 100, 2) if len(c) > n else None
        hi, lo = max(c), min(c)
        out[t] = {"price": round(last, 2), "date": dt.isoformat(), "chg": round(last - c[-2], 2), "d1": r(1), "d5": r(5),
                  "m1": r(21), "ytd": round((last / ytd_base - 1) * 100, 2) if ytd_base else None,
                  "hi52": round(hi, 2), "lo52": round(lo, 2), "pos52": round((last - lo) / (hi - lo) * 100) if hi > lo else None,
                  "spark": [round(x, 2) for x in c[-60:]]}
    return out


def market_caps_and_earnings(tickers: list[str]) -> dict[str, dict]:
    import yfinance as yf
    out = {}
    today = date.today()
    for t in tickers:
        info = {}
        try:
            info["mcap"] = float(yf.Ticker(t).fast_info["marketCap"]) or None
        except Exception:
            pass
        try:
            cal = yf.Ticker(t).calendar or {}
            days = [d for d in cal.get("Earnings Date", []) if isinstance(d, date) and d >= today]
            if days:
                info["earnings"] = min(days).isoformat()
        except Exception:
            pass
        out[t] = info
    return out


# ---------------------------------------------------------------- SEC 財報

def _entries(facts: dict, tag: str) -> dict[tuple[str, str], float]:
    """同一期間（start, end）取最晚申報的數字。"""
    latest: dict[tuple[str, str], tuple[str, float]] = {}
    for u in (facts.get("us-gaap", {}).get(tag) or {}).get("units", {}).get("USD") or []:
        if not u.get("start") or u.get("form") not in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
            continue
        key = (u["start"], u["end"])
        if key not in latest or u.get("filed", "") >= latest[key][0]:
            latest[key] = (u.get("filed", ""), float(u["val"]))
    return {k: v for k, (_, v) in latest.items()}


def merged_quarters(facts: dict, tags: list[str]) -> dict[str, float]:
    """公司會換 tag（例如 JPM 2015 年後改用 RevenuesNetOfInterestExpense）：最近還在用的 tag 優先，其他只補空缺。"""
    per = [(t, quarters(_entries(facts, t))) for t in tags]
    per = [(i, q) for i, (_, q) in enumerate(per) if q]
    per.sort(key=lambda x: (max(x[1]), -x[0]), reverse=True)
    out: dict[str, float] = {}
    for _, q in per:
        for e, v in q.items():
            out.setdefault(e, v)
    return dict(sorted(out.items()))


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def quarters(entries: dict[tuple[str, str], float]) -> dict[str, float]:
    """拆成單季：三個月期直接用；累計數字（6、9、12 個月）用相鄰兩期相減補出來。"""
    q: dict[str, float] = {}
    for (s, e), v in entries.items():
        if 80 <= _days(s, e) <= 115:
            q[e] = v
    by_start: dict[str, list[tuple[str, float]]] = {}
    for (s, e), v in entries.items():
        by_start.setdefault(s, []).append((e, v))
    for s, xs in by_start.items():
        xs.sort()
        for (e1, v1), (e2, v2) in zip(xs, xs[1:]):
            if e2 not in q and 80 <= _days(e1, e2) <= 115:
                q[e2] = v2 - v1
    return dict(sorted(q.items()))


def ttm(q: dict[str, float], end: str | None = None) -> float | None:
    ends = [e for e in q if end is None or e <= end][-4:]
    if len(ends) < 4 or any(not 80 <= _days(a, b) <= 115 for a, b in zip(ends, ends[1:])):
        return None
    return sum(q[e] for e in ends)


def year_ago(q: dict[str, float], end: str) -> str | None:
    return next((e for e in q if 350 <= _days(e, end) <= 380), None)


def fundamentals(cik: int) -> dict | None:
    facts = sec_get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json").json().get("facts", {})
    if "us-gaap" not in facts:
        return None
    qs = {k: merged_quarters(facts, tags) for k, tags in TAGS.items()}
    rev = qs["revenue"]
    if not rev:
        return None
    last = list(rev)[-1]
    ya = year_ago(rev, last)
    f = {"quarter_end": last, "rev_q": rev[last],
         "rev_yoy": round((rev[last] / rev[ya] - 1) * 100, 1) if ya and rev[ya] > 0 else None,
         "rev_ttm": ttm(rev), "ni_ttm": ttm(qs["net_income"]), "rev_q_series": [[e, rev[e]] for e in list(rev)[-8:]]}
    ya_ttm = ttm(rev, ya) if ya else None
    f["rev_ttm_yoy"] = round((f["rev_ttm"] / ya_ttm - 1) * 100, 1) if f["rev_ttm"] and ya_ttm else None
    f["net_margin"] = round(f["ni_ttm"] / f["rev_ttm"] * 100, 1) if f["ni_ttm"] is not None and f["rev_ttm"] else None
    ocf, capex = ttm(qs["ocf"]), ttm(qs["capex"])
    f["fcf_ttm"] = ocf - capex if ocf is not None and capex is not None else None
    return f


def recent_filings(cik: int, ticker: str, name: str, since: str) -> list[dict]:
    d = sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    r = d["filings"]["recent"]
    out = []
    for i, form in enumerate(r["form"]):
        if r["filingDate"][i] < since:
            break
        if form not in ("8-K", "10-Q", "10-K", "20-F", "8-K/A"):
            continue
        items = [x.strip() for x in (r.get("items", [""] * len(r["form"]))[i] or "").split(",") if x.strip()]
        labels = [ITEMS_8K[x] for x in items if x in ITEMS_8K]
        if form.startswith("8-K") and not labels:
            continue  # 只有 9.01（附件）之類的就略過
        acc = r["accessionNumber"][i]
        out.append({"ticker": ticker, "name": name, "form": form, "filed": r["filingDate"][i], "items": labels,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{r['primaryDocument'][i]}"})
    return out


# ---------------------------------------------------------------- 主程式

def main() -> int:
    whales = json.loads(WHALES.read_text(encoding="utf-8")) if WHALES.exists() else {}
    names = {t: n for g in GROUPS.values() for t, n in g}
    groups = {k: [t for t, _ in v] for k, v in GROUPS.items()}
    # 大佬共識：13F 最多位大佬持有、且不在上面清單的前 8 檔
    wt = sorted((whales.get("by_ticker") or {}).values(), key=lambda x: (-x["n"], -x.get("value", 0)))
    wt = [{**x, "ticker": x["ticker"].replace("/", "-")} for x in wt]
    extra = [x for x in wt if x["ticker"] not in names and x["n"] >= 2][:8]
    groups["大佬共識"] = [x["ticker"] for x in extra]
    names.update({x["ticker"]: x["name"].title() for x in extra})
    stocks = [t for g in groups.values() for t in g]

    px = prices([t for t, _ in INDICES] + [t for t, _ in SECTORS] + stocks)
    if not px:
        log("⛔ Yahoo 報價全部失敗")
        return 1
    meta = market_caps_and_earnings(stocks)

    supply = json.loads(SUPPLY.read_text(encoding="utf-8")) if SUPPLY.exists() else {}
    tw_links: dict[str, list[dict]] = {}
    for t in supply.get("tw", []):
        for code in t.get("links", []):
            tw_links.setdefault(code, []).append({"code": t["code"], "name": t["name"], "chg_1d": t.get("chg_1d")})

    ciks, sec_ok = {}, True
    try:
        tick = sec_get("https://www.sec.gov/files/company_tickers.json").json()
        ciks = {v["ticker"].upper(): int(v["cik_str"]) for v in tick.values()}
    except SecBlocked as exc:
        log(f"⚠️ SEC 讀不到，財報與申報略過：{exc}")
        sec_ok = False

    since = (date.today() - timedelta(days=FILING_DAYS)).isoformat()
    rows, filings = [], []
    for t in stocks:
        if t not in px:
            continue
        row = {"ticker": t, "name": names.get(t, t), **px[t], **meta.get(t, {}),
               "whales": [h["person"] for h in ((whales.get("by_ticker") or {}).get(t) or {}).get("holders", [])],
               "tw": sorted(tw_links.get(t, []), key=lambda x: -(x.get("chg_1d") or 0))[:4]}
        cik = ciks.get(t.replace("-", "."), ciks.get(t))
        if sec_ok and cik:
            try:
                row["fin"] = fundamentals(cik)
                filings += recent_filings(cik, t, row["name"], since)
            except SecBlocked as exc:
                log(f"⚠️ SEC 中途被擋，後面略過：{exc}")
                sec_ok = False
            except Exception as exc:
                log(f"⚠️ {t} 財報讀取失敗：{exc}")
        fin = row.get("fin") or {}
        if row.get("mcap") and fin.get("ni_ttm") and fin["ni_ttm"] > 0:
            row["pe"] = round(row["mcap"] / fin["ni_ttm"], 1)
        rows.append(row)
        time.sleep(0.05)

    out = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
        "indices": [{"ticker": t, "name": n, **px[t]} for t, n in INDICES if t in px],
        "sectors": [{"ticker": t, "name": n, **px[t]} for t, n in SECTORS if t in px],
        "groups": groups, "stocks": rows,
        "filings": sorted(filings, key=lambda f: (f["filed"], f["ticker"]), reverse=True),
        "sec_ok": sec_ok,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    n_fin = sum(1 for r in rows if r.get("fin"))
    log(f"✅ 美股：{len(out['indices'])} 指數、{len(out['sectors'])} 類股、{len(rows)} 檔（{n_fin} 檔有 SEC 財報）、近 {FILING_DAYS} 天申報 {len(filings)} 筆")
    return 0


if __name__ == "__main__":
    sys.exit(main())
