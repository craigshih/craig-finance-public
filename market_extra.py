"""
台股頁的進階資料（輸出 data/market/extra.json，歷史另存成 contrib_history / valuation_history / futures_history）：

1. 誰在推指數：每檔上市普通股對加權指數的貢獻點數＝市值變化 ÷ 指數除數（除數＝前一日總市值 ÷ 前一日指數），
   拆成台積電、其他市值前十大、其餘上市股票。第一次執行回補近 60 個交易日（證交所每日收盤行情 MI_INDEX）。
2. 估值位置：上市大盤本益比、股價淨值比、殖利率（市值加權；本益比只算有獲利的公司），
   跟近 10 年比在第幾百分位。歷史第一次執行時，每月取一個交易日回補（證交所 BWIBBU_d＋MI_INDEX）。
3. 期貨籌碼：外資台指期淨未平倉、散戶小台＋微台多空比（全市場未平倉扣掉三大法人；微台 5 口算 1 口小台）、
   Put/Call 未平倉比。資料：期交所 OpenAPI；歷史從現在開始每天累積。

股數用證交所公司基本資料的「已發行普通股數」（回補歷史時沿用現在的股數，是近似值）。
"""

import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
DIR = ROOT / "data" / "market"
OUT = DIR / "extra.json"
H_CONTRIB = DIR / "contrib_history.json"
H_VAL = DIR / "valuation_history.json"
H_FUT = DIR / "futures_history.json"
TAIPEI = timezone(timedelta(hours=8))
UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)"
TWSE_RWD = "https://www.twse.com.tw/rwd/zh/afterTrading"
TAIFEX = "https://openapi.taifex.com.tw/v1"
CONTRIB_DAYS = 60
VAL_YEARS = 10


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def get_json(url: str, params: dict | None = None, pause: float = 0.0):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=60)
            if r.status_code == 200:
                time.sleep(pause)
                return r.json()
            log(f"⚠️ {url} {r.status_code}")
        except (requests.RequestException, ValueError) as exc:
            log(f"⚠️ {url}：{exc}")
        time.sleep(5 * (attempt + 1))
    return None


def num(x):
    try:
        s = str(x).replace(",", "").strip()
        return float(s) if s not in ("", "-", "--", "X", "NULL") else None
    except ValueError:
        return None


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def is_common(code: str) -> bool:
    return bool(re.fullmatch(r"[1-9]\d{3}", code))


def shares() -> dict[str, float]:
    rows = get_json("https://openapi.twse.com.tw/v1/opendata/t187ap03_L") or []
    out = {}
    for r in rows:
        n = num(r.get("已發行普通股數或TDR原股發行股數"))
        if n and is_common(r.get("公司代號", "")):
            out[r["公司代號"]] = n
    return out


def day_quotes(d: str) -> dict[str, dict] | None:
    """證交所某一天的全部收盤行情：{代號: {name, close, prev}}；那天沒開盤回 None。"""
    j = get_json(f"{TWSE_RWD}/MI_INDEX", {"date": d.replace("-", ""), "type": "ALLBUT0999", "response": "json"}, pause=2.5)
    if not j or j.get("stat") != "OK":
        return None
    for t in j.get("tables", []):
        f = t.get("fields") or []
        if "收盤價" in f and len(t.get("data") or []) > 500:
            i = {k: f.index(k) for k in ("證券代號", "證券名稱", "收盤價", "漲跌(+/-)", "漲跌價差")}
            out = {}
            for r in t["data"]:
                code, close, diff = r[i["證券代號"]], num(r[i["收盤價"]]), num(r[i["漲跌價差"]])
                if not is_common(code) or not close:
                    continue
                sign = -1 if "-" in re.sub(r"<[^>]+>", "", r[i["漲跌(+/-)"]]) else 1
                out[code] = {"name": r[i["證券名稱"]].replace("*", "").strip(), "close": close,
                             "prev": close - sign * (diff or 0)}
            return out
    return None


# ---------------------------------------------------------------- 1. 誰在推指數

def contrib_day(q: dict, sh: dict, idx_prev: float, idx_now: float) -> dict:
    caps_prev = {c: x["prev"] * sh[c] for c, x in q.items() if c in sh}
    divisor = sum(caps_prev.values()) / idx_prev
    pts = {c: (q[c]["close"] - q[c]["prev"]) * sh[c] / divisor for c in caps_prev}
    top10 = sorted(caps_prev, key=lambda c: -caps_prev[c])[:10]
    tsmc = pts.get("2330", 0.0)
    other10 = sum(pts[c] for c in top10 if c != "2330")
    rest = sum(v for c, v in pts.items() if c not in top10)
    return {"tsmc": round(tsmc, 1), "top10": round(other10, 1), "rest": round(rest, 1),
            "index": round(idx_now - idx_prev, 1), "gap": round(idx_now - idx_prev - tsmc - other10 - rest, 1),
            "pts": pts, "top10_codes": top10, "weights": {c: caps_prev[c] / sum(caps_prev.values()) for c in top10}}


def index_closes() -> dict[str, float]:
    m = load(DIR / "latest.json", {})
    tw = next((i for i in m.get("indices", []) if i.get("ticker") == "^TWII"), None)
    return {r[0]: r[4] for r in (tw or {}).get("ohlc", [])}


def build_contrib(sh: dict) -> dict | None:
    idx = index_closes()
    days = sorted(idx)
    if len(days) < 2:
        log("⚠️ 沒有加權指數歷史，略過誰在推指數")
        return None
    hist = load(H_CONTRIB, {})
    want = days[-CONTRIB_DAYS:]
    latest = None
    for d in want:
        if d in hist and d != days[-1]:
            continue
        q = day_quotes(d)
        prev_day = days[days.index(d) - 1] if days.index(d) > 0 else None
        if not q or not prev_day:
            continue
        r = contrib_day(q, sh, idx[prev_day], idx[d])
        hist[d] = {k: r[k] for k in ("tsmc", "top10", "rest", "index", "gap")}
        if d == days[-1]:
            names = {c: q[c]["name"] for c in q}
            ranked = sorted(r["pts"].items(), key=lambda kv: kv[1])
            latest = {"date": d, **hist[d],
                      "push": [{"code": c, "name": names[c], "pts": round(v, 1), "pct": round((q[c]["close"] / q[c]["prev"] - 1) * 100, 2)}
                               for c, v in ranked[::-1][:5] if v > 0],
                      "drag": [{"code": c, "name": names[c], "pts": round(v, 1), "pct": round((q[c]["close"] / q[c]["prev"] - 1) * 100, 2)}
                               for c, v in ranked[:5] if v < 0],
                      "tsmc_weight": round(r["weights"].get("2330", 0) * 100, 1)}
    hist = {d: hist[d] for d in sorted(hist)[-CONTRIB_DAYS:]}
    save(H_CONTRIB, hist)
    if not latest:
        last = sorted(hist)[-1] if hist else None
        latest = {"date": last, **hist[last], "push": [], "drag": []} if last else None
    if not latest:
        return None
    periods = {}
    keys = sorted(hist)
    for label, n in (("5 日", 5), ("20 日", 20), ("60 日", 60)):
        sel = keys[-n:]
        periods[label] = {k: round(sum(hist[d][k] for d in sel), 1) for k in ("tsmc", "top10", "rest", "index")}
    return {**latest, "periods": periods, "history": [{"date": d, **hist[d]} for d in keys]}


# ---------------------------------------------------------------- 2. 估值位置

def valuation_on(d: str, sh: dict, pe_rows=None, q=None) -> dict | None:
    if pe_rows is None:
        j = get_json(f"{TWSE_RWD}/BWIBBU_d", {"date": d.replace("-", ""), "selectType": "ALL", "response": "json"}, pause=2.5)
        if not j or j.get("stat") != "OK":
            return None
        f = j["fields"]
        ip, iy, ib = f.index("本益比"), f.index("殖利率(%)"), f.index("股價淨值比")
        pe_rows = {r[0]: (num(r[ip]), num(r[iy]), num(r[ib])) for r in j["data"] if is_common(r[0])}
    if q is None:
        q = day_quotes(d)
    if not q:
        return None
    cap = {c: q[c]["close"] * sh[c] for c in pe_rows if c in q and c in sh}
    total = sum(cap.values())
    if total <= 0:
        return None
    earn = sum(cap[c] / pe_rows[c][0] for c in cap if pe_rows[c][0] and pe_rows[c][0] > 0)
    book = sum(cap[c] / pe_rows[c][2] for c in cap if pe_rows[c][2] and pe_rows[c][2] > 0)
    div = sum(cap[c] * (pe_rows[c][1] or 0) / 100 for c in cap)
    return {"pe": round(total / earn, 2) if earn else None, "pb": round(total / book, 2) if book else None,
            "yield": round(div / total * 100, 2), "cap_trillion": round(total / 1e12, 1)}


def first_trading_days(years: int) -> list[str]:
    """每個月第一個平日（遇到休市由 day_quotes 回 None 時往後找）。"""
    out = []
    today = date.today()
    y, m = today.year - years, today.month
    while (y, m) < (today.year, today.month):
        out.append(f"{y}-{m:02d}-01")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def build_valuation(sh: dict, today_q: dict | None, today: str | None) -> dict | None:
    hist = load(H_VAL, {})
    # 回補：每月一點（只補還沒有的月份），每次最多補 30 個月，避免單次跑太久
    filled = 0
    have_months = {d[:7] for d in hist}
    for first in first_trading_days(VAL_YEARS):
        if first[:7] in have_months or filled >= 30:
            continue
        d0 = date.fromisoformat(first)
        for k in range(7):
            d = (d0 + timedelta(days=k)).isoformat()
            if date.fromisoformat(d).weekday() >= 5:
                continue
            v = valuation_on(d, sh)
            if v:
                hist[d] = v
                filled += 1
                break
    # 今天
    if today and today_q:
        rows = get_json("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL") or []
        pe_rows = {r["Code"]: (num(r.get("PEratio")), num(r.get("DividendYield")), num(r.get("PBratio")))
                   for r in rows if is_common(r.get("Code", ""))}
        v = valuation_on(today, sh, pe_rows, today_q) if pe_rows else None
        if v:
            hist[today] = v
    save(H_VAL, dict(sorted(hist.items())))
    if not hist:
        return None
    last = sorted(hist)[-1]
    cutoff = (date.fromisoformat(last) - timedelta(days=365 * VAL_YEARS)).isoformat()
    window = [v for d, v in hist.items() if d >= cutoff]

    def pctile(key):
        xs = [v[key] for v in window if v.get(key) is not None]
        x = hist[last].get(key)
        return round(sum(1 for v in xs if v <= x) / len(xs) * 100) if xs and x is not None else None

    med = lambda key: sorted(v[key] for v in window if v.get(key))[len(window) // 2] if window else None
    return {"date": last, **hist[last], "n_points": len(window), "since": min(d for d in hist if d >= cutoff),
            "pct": {k: pctile(k) for k in ("pe", "pb", "yield")}, "median": {k: med(k) for k in ("pe", "pb", "yield")},
            "series": [{"date": d, "pe": v.get("pe")} for d, v in sorted(hist.items()) if d >= cutoff]}


# ---------------------------------------------------------------- 3. 期貨籌碼

def build_futures() -> dict | None:
    inst = get_json(f"{TAIFEX}/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate") or []
    rep = get_json(f"{TAIFEX}/DailyMarketReportFut") or []
    pc = get_json(f"{TAIFEX}/PutCallRatio") or []
    if not inst or not rep:
        log("⚠️ 期交所資料讀不到")
        return None
    day = inst[0]["Date"]
    d = f"{day[:4]}-{day[4:6]}-{day[6:]}"

    def inst_net(contract, who=None):
        return sum(num(x["OpenInterest(Net)"]) or 0 for x in inst
                   if x["ContractCode"] == contract and (who is None or x["Item"].startswith(who)))  # 期交所寫「外資及陸資」

    def total_oi(code):
        return sum(num(x["OpenInterest"]) or 0 for x in rep if x["Contract"] == code and x["TradingSession"] == "一般")

    mtx_oi, tmf_oi = total_oi("MTX"), total_oi("TMF")
    retail = -(inst_net("小型臺指期貨") + inst_net("微型臺指期貨") / 5)
    base = mtx_oi + tmf_oi / 5
    row = {"date": d, "foreign_tx": int(inst_net("臺股期貨", "外資")),
           "retail_ratio": round(retail / base * 100, 2) if base else None,
           "retail_mtx": round(-inst_net("小型臺指期貨") / mtx_oi * 100, 2) if mtx_oi else None,
           "retail_tmf": round(-inst_net("微型臺指期貨") / tmf_oi * 100, 2) if tmf_oi else None}
    pcs = {f'{x["Date"][:4]}-{x["Date"][4:6]}-{x["Date"][6:]}': num(x["PutCallOIRatio%"]) for x in pc}
    row["pc_oi"] = pcs.get(d)
    hist = load(H_FUT, {})
    hist[d] = row
    for k, v in pcs.items():  # P/C 比 OpenAPI 給近 20 天，順便補進歷史
        hist.setdefault(k, {"date": k})["pc_oi"] = v
    hist = dict(sorted(hist.items())[-400:])
    save(H_FUT, hist)
    keys = sorted(k for k in hist if hist[k].get("retail_ratio") is not None)
    prev = hist[keys[-2]] if len(keys) > 1 else None
    rr = [hist[k]["retail_ratio"] for k in keys[-250:]]
    pct = round(sum(1 for v in rr if v <= row["retail_ratio"]) / len(rr) * 100) if rr and row["retail_ratio"] is not None else None
    return {**row, "prev": prev, "retail_pct": pct, "n_days": len(rr),
            "pc_series": [{"date": k, "v": hist[k]["pc_oi"]} for k in sorted(hist) if hist[k].get("pc_oi") is not None][-60:],
            "series": [{"date": k, **{f: hist[k].get(f) for f in ("foreign_tx", "retail_ratio")}} for k in keys][-120:]}


# ---------------------------------------------------------------- 主程式

def main() -> int:
    DIR.mkdir(parents=True, exist_ok=True)
    sh = shares()
    if len(sh) < 500:
        log(f"⛔ 股數資料只有 {len(sh)} 檔")
        return 1
    out = {"generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes")}
    try:
        out["contrib"] = build_contrib(sh)
    except Exception as exc:  # 單一區塊失敗不影響其他
        log(f"⚠️ 誰在推指數失敗：{exc}")
    try:
        idx = index_closes()
        today = sorted(idx)[-1] if idx else None
        out["valuation"] = build_valuation(sh, day_quotes(today) if today else None, today)
    except Exception as exc:
        log(f"⚠️ 估值位置失敗：{exc}")
    try:
        out["futures"] = build_futures()
    except Exception as exc:
        log(f"⚠️ 期貨籌碼失敗：{exc}")
    save(OUT, out)
    c, v, f = out.get("contrib"), out.get("valuation"), out.get("futures")
    log(f"✅ 台股進階：貢獻 {c and c['date']}（{len((c or {}).get('history', []))} 天）、估值 {v and v['date']} "
        f"本益比 {v and v['pe']}（{v and v['pct']['pe']} 百分位，{v and v['n_points']} 點）、期貨 {f and f['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
