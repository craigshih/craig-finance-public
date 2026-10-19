"""
台股頁的「市場寬度」「加權 vs 等權」「成交金額」「類股輪動圖」資料（輸出 data/market/breadth.json）。

資料：Yahoo Finance 全部上市（.TW）＋上櫃（.TWO）普通股近 2 年日線（一次批次下載約 1 分鐘），每次重算、不需要累積。
  - 市場寬度：騰落線（每天上漲家數 − 下跌家數，逐日累加）、52 週新高／新低家數、站上 20／60／240 日線的股票比例
    （用還原權值價 Adj Close，除權息不會被誤判成跌破均線）
  - 加權 vs 等權：加權指數 vs 所有上市普通股每天平均漲跌累乘
  - 成交金額：每檔收盤價 × 成交股數加總（上市＋上櫃普通股，約略值）與 20 日平均
  - 類股輪動圖（RRG）：族群等權指數 ÷ 加權指數＝相對強度 RS；
      相對強弱 RS-Ratio＝100 × RS ÷ 近 50 日 RS 平均（>100 比大盤強）；
      動能 RS-Momentum＝100 × 今天 RS-Ratio ÷ 10 個交易日前的 RS-Ratio（>100 越來越強）；每週取一點畫軌跡。
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
OUT = ROOT / "data" / "market" / "breadth.json"
ADVISOR = ROOT / "data" / "advisor" / "stocks.json"
TAIPEI = timezone(timedelta(hours=8))
UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def universe() -> dict[str, str]:
    """代號 → Yahoo 代碼（上市 .TW、上櫃 .TWO），只要普通股。"""
    out = {}
    for url, key, suffix in (("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "Code", ".TW"),
                             ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", "SecuritiesCompanyCode", ".TWO")):
        try:
            for r in requests.get(url, headers={"User-Agent": UA}, timeout=60).json():
                c = r.get(key, "")
                if re.fullmatch(r"[1-9]\d{3}", c):
                    out.setdefault(c, c + suffix)
        except (requests.RequestException, ValueError) as exc:
            log(f"⚠️ {url}：{exc}")
    return out


def industries() -> dict[str, str]:
    try:
        s = json.loads(ADVISOR.read_text(encoding="utf-8"))["stocks"]
        return {c: x["industry"] for c, x in s.items() if x.get("industry")}
    except (OSError, json.JSONDecodeError, KeyError):
        return {}


def rrg(index_series, rs_base, groups: dict[str, list[str]], adj, weeks: int = 8) -> list[dict]:
    """每個族群：等權指數 → 相對強度 → RS-Ratio、RS-Momentum，回傳最近 weeks 週（每週最後一個交易日）的軌跡。"""
    import pandas as pd

    rets = adj.pct_change(fill_method=None)
    out = []
    for name, codes in groups.items():
        cols = [c for c in codes if c in rets.columns]
        if len(cols) < 2:
            continue
        ew = (1 + rets[cols].mean(axis=1, skipna=True).fillna(0)).cumprod()
        rs = ew / rs_base
        ratio = 100 * rs / rs.rolling(50).mean()
        mom = 100 * ratio / ratio.shift(10)
        df = pd.DataFrame({"x": ratio, "y": mom}).dropna()
        if df.empty:
            continue
        weekly = df.groupby(df.index.to_period("W")).tail(1).tail(weeks)
        trail = [{"date": d.strftime("%Y-%m-%d"), "x": round(float(r.x), 2), "y": round(float(r.y), 2)} for d, r in weekly.iterrows()]
        last = trail[-1]
        quad = ("領先" if last["y"] >= 100 else "轉弱") if last["x"] >= 100 else ("改善" if last["y"] >= 100 else "落後")
        prev = trail[-2] if len(trail) > 1 else None
        pq = None
        if prev:
            pq = ("領先" if prev["y"] >= 100 else "轉弱") if prev["x"] >= 100 else ("改善" if prev["y"] >= 100 else "落後")
        r20 = float(ew.iloc[-1] / ew.iloc[-21] - 1) * 100 if len(ew) > 21 else None
        out.append({"name": name, "n": len(cols), "trail": trail, "quadrant": quad, "prev_quadrant": pq,
                    "ret_20d": round(r20, 2) if r20 is not None else None})
    return out


def official_latest() -> tuple[str | None, float | None, dict[str, tuple[float, float, float]]]:
    """官方最新一個交易日：加權指數收盤（證交所 MIS）、每檔（收盤, 前一日收盤, 成交股數）（上市 MI_INDEX＋上櫃 OpenAPI）。"""
    rows: dict[str, tuple[float, float, float]] = {}
    num = lambda x: float(str(x).replace(",", "")) if str(x).replace(",", "").replace(".", "", 1).lstrip("-").isdigit() else None
    try:
        m = requests.get("https://mis.twse.com.tw/stock/api/getStockInfo.jsp?json=1&delay=0&ex_ch=tse_t00.tw",
                         headers={"User-Agent": "Mozilla/5.0", "Referer": "https://mis.twse.com.tw/stock/index.jsp"}, timeout=20).json()["msgArray"][0]
        day, idx = f'{m["d"][:4]}-{m["d"][4:6]}-{m["d"][6:]}', num(m["z"])
    except Exception as exc:  # noqa: BLE001
        log(f"⚠️ 讀不到官方加權指數：{exc}")
        return None, None, rows
    try:
        j = requests.get("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
                         params={"date": day.replace("-", ""), "type": "ALLBUT0999", "response": "json"},
                         headers={"User-Agent": UA}, timeout=60).json()
        for t in j.get("tables", []):
            f = t.get("fields") or []
            if "收盤價" in f and len(t.get("data") or []) > 500:
                ic, iv, isg, idf = f.index("收盤價"), f.index("成交股數"), f.index("漲跌(+/-)"), f.index("漲跌價差")
                for r in t["data"]:
                    close, diff, v = num(r[ic]), num(r[idf]), num(r[iv])
                    if re.fullmatch(r"[1-9]\d{3}", r[0]) and close:
                        sign = -1 if "-" in re.sub(r"<[^>]+>", "", r[isg]) else 1
                        rows[r[0]] = (close, close - sign * (diff or 0), v or 0)
        roc = f"{int(day[:4]) - 1911}{day[5:7]}{day[8:]}"
        for r in requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers={"User-Agent": UA}, timeout=60).json():
            c, close, chg = r.get("SecuritiesCompanyCode", ""), num(r.get("Close")), num(r.get("Change"))
            if r.get("Date") == roc and re.fullmatch(r"[1-9]\d{3}", c) and close:
                rows[c] = (close, close - (chg or 0), num(r.get("TradingShares")) or 0)
    except (requests.RequestException, ValueError) as exc:
        log(f"⚠️ 官方收盤行情讀取失敗：{exc}")
    return day, idx, rows


def append_official(adj, raw, vol, taiex):
    """Yahoo 的日線常慢一天：官方已經有更新的交易日，就用官方收盤補一列（還原價＝前一天還原價 × 當天漲跌比）。"""
    import pandas as pd

    day, idx, rows = official_latest()
    last = adj.index[-1].strftime("%Y-%m-%d")
    if not day or day <= last or not idx or len(rows) < len(adj.columns) * 0.8:
        return adj, raw, vol, taiex
    ts = pd.Timestamp(day)
    prev_adj = adj.iloc[-1]
    new_adj, new_raw, new_vol = {}, {}, {}
    for c in adj.columns:
        if c in rows and rows[c][1]:
            close, prev, v = rows[c]
            new_raw[c], new_vol[c] = close, v
            if prev_adj.get(c) == prev_adj.get(c):  # 不是 NaN
                new_adj[c] = prev_adj[c] * close / prev
    adj = pd.concat([adj, pd.DataFrame(new_adj, index=[ts])])
    raw = pd.concat([raw, pd.DataFrame(new_raw, index=[ts])])
    vol = pd.concat([vol, pd.DataFrame(new_vol, index=[ts])])
    taiex = pd.concat([taiex, pd.Series([idx], index=[ts])])
    log(f"  Yahoo 只到 {last}，用證交所／櫃買官方收盤補上 {day}（{len(new_adj)} 檔）")
    return adj, raw, vol, taiex


def download(tickers: list[str]):
    """分批下載（每批 300 檔），失敗的再補抓一次；Yahoo 偶爾會擋大量請求。"""
    import time

    import pandas as pd
    import yfinance as yf

    frames = []
    def fetch(batch):
        df = yf.download(batch, period="2y", interval="1d", auto_adjust=False, progress=False, threads=True, group_by="column")
        return df[["Adj Close", "Close", "Volume"]] if not df.empty else None
    for i in range(0, len(tickers), 300):
        f = fetch(tickers[i:i + 300])
        if f is not None:
            frames.append(f)
        time.sleep(2)
    df = pd.concat(frames, axis=1) if frames else pd.DataFrame()
    got = set(df["Adj Close"].columns[df["Adj Close"].notna().sum() > 60]) if not df.empty else set()
    missing = [t for t in tickers if t not in got]
    if missing:
        log(f"  補抓 {len(missing)} 檔")
        time.sleep(10)
        for i in range(0, len(missing), 200):
            f = fetch(missing[i:i + 200])
            if f is not None:
                df = pd.concat([df.drop(columns=[c for c in f.columns if c in df.columns]), f], axis=1)
            time.sleep(3)
    return df


def main() -> int:
    from supply_map import PEER_GROUPS

    uni = universe()
    if len(uni) < 1000:
        log(f"⛔ 股票清單只有 {len(uni)} 檔")
        return 1
    tickers = list(uni.values()) + ["^TWII"]
    df = download(tickers)
    to_code = {v: k for k, v in uni.items()}
    adj = df["Adj Close"].rename(columns=to_code)
    raw = df["Close"].rename(columns=to_code)
    vol = df["Volume"].rename(columns=to_code)
    taiex = adj.pop("^TWII").dropna()
    raw = raw.drop(columns=["^TWII"], errors="ignore")
    vol = vol.drop(columns=["^TWII"], errors="ignore")
    adj = adj.loc[taiex.index]  # 只留大盤有開盤的日子
    raw, vol = raw.loc[adj.index], vol.loc[adj.index]
    stock_cols = [c for c in adj.columns if adj[c].notna().sum() > 60]
    if len(stock_cols) < 1500:
        log(f"⛔ 只下載到 {len(stock_cols)} 檔（Yahoo 可能暫時擋住），保留上一份資料")
        return 1
    adj, raw, vol = adj[stock_cols], raw[stock_cols], vol[stock_cols]
    # 最後一天如果只有少數股票有資料（Yahoo 還沒更新完），就不算那一天
    while len(adj) and adj.iloc[-1].notna().sum() < len(stock_cols) * 0.8:
        adj, raw, vol = adj.iloc[:-1], raw.iloc[:-1], vol.iloc[:-1]
    taiex = taiex.loc[adj.index]
    # Yahoo 有些日子只有部分股票有資料：涵蓋不到八成的日子整天不算；個股零星缺的幾天用前一天價格補（最多 5 天）
    keep = raw.notna().sum(axis=1) >= len(stock_cols) * 0.8
    adj, raw, vol, taiex = adj[keep], raw[keep], vol[keep], taiex[keep]
    adj = adj.ffill(limit=5)
    adj, raw, vol, taiex = append_official(adj, raw, vol, taiex)
    listed = [c for c in stock_cols if uni[c].endswith(".TW")]
    days = adj.index
    one_year = days[-250:] if len(days) >= 250 else days
    d = lambda x: x.strftime("%Y-%m-%d")

    rets = adj.pct_change(fill_method=None)
    up, down = (rets > 0).sum(axis=1), (rets < 0).sum(axis=1)
    ad = (up - down).loc[one_year].cumsum()

    hi250 = adj.rolling(250, min_periods=230).max().shift(1)
    lo250 = adj.rolling(250, min_periods=230).min().shift(1)
    new_hi, new_lo = (adj > hi250).sum(axis=1), (adj < lo250).sum(axis=1)

    above = {}
    for n in (20, 60, 240):
        ma = adj.rolling(n, min_periods=int(n * 0.9)).mean()
        valid = ma.notna() & adj.notna()
        above[n] = ((adj > ma) & valid).sum(axis=1) / valid.sum(axis=1).replace(0, float("nan")) * 100

    ew = (1 + rets[listed].mean(axis=1, skipna=True).fillna(0)).loc[one_year].cumprod()
    tx = taiex.loc[one_year]
    turnover = (raw * vol).sum(axis=1, min_count=1) / 1e8  # 億元
    to20 = turnover.rolling(20).mean()

    m60 = above[60].dropna()
    pct60 = round(float((m60 <= m60.iloc[-1]).mean() * 100)) if len(m60) else None

    peer_groups = {name: [c for c, _ in members] for name, members, *_ in PEER_GROUPS}
    ind = industries()
    ind_groups: dict[str, list[str]] = {}
    for c in stock_cols:
        if ind.get(c):
            ind_groups.setdefault(ind[c], []).append(c)
    ind_groups = {k: v for k, v in ind_groups.items() if len(v) >= 5}
    tx_full = taiex
    out = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
        "date": d(days[-1]), "n_stocks": len(stock_cols),
        "today": {"up": int(up.iloc[-1]), "down": int(down.iloc[-1]), "new_hi": int(new_hi.iloc[-1]), "new_lo": int(new_lo.iloc[-1]),
                  "above20": round(float(above[20].iloc[-1]), 1), "above60": round(float(above[60].iloc[-1]), 1),
                  "above240": round(float(above[240].iloc[-1]), 1) if above[240].notna().any() else None,
                  "above60_pct": pct60, "above60_days": len(m60),
                  "turnover": round(float(turnover.iloc[-1])), "turnover_ma20": round(float(to20.iloc[-1])),
                  "ew_1y": round(float(ew.iloc[-1] - 1) * 100, 1), "taiex_1y": round(float(tx.iloc[-1] / tx.iloc[0] - 1) * 100, 1)},
        "ad_line": [{"date": d(i), "v": int(v)} for i, v in ad.items()],
        "taiex_1y": [{"date": d(i), "v": round(float(v), 1)} for i, v in tx.items()],
        "new_hl": [{"date": d(i), "hi": int(new_hi[i]), "lo": int(new_lo[i])} for i in one_year],
        "above": [{"date": d(i), "m20": round(float(above[20][i]), 1), "m60": round(float(above[60][i]), 1),
                   "m240": round(float(above[240][i]), 1) if above[240][i] == above[240][i] else None}
                  for i in days if above[60][i] == above[60][i]],
        "ew_vs_cap": [{"date": d(i), "cap": round(float(tx[i] / tx.iloc[0] - 1) * 100, 2), "ew": round(float(ew[i] - 1) * 100, 2)} for i in one_year],
        "turnover": [{"date": d(i), "v": round(float(turnover[i])), "ma20": round(float(to20[i])) if to20[i] == to20[i] else None} for i in one_year],
        "rrg": {"peer": rrg(None, tx_full, peer_groups, adj), "industry": rrg(None, tx_full, ind_groups, adj)},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    t = out["today"]
    log(f"✅ 市場寬度 {out['date']}：{out['n_stocks']} 檔，漲 {t['up']}／跌 {t['down']}、新高 {t['new_hi']}／新低 {t['new_lo']}、"
        f"站上季線 {t['above60']}%（第 {pct60} 百分位）、成交 {t['turnover']:,} 億、輪動 {len(out['rrg']['peer'])}＋{len(out['rrg']['industry'])} 群")
    return 0


if __name__ == "__main__":
    sys.exit(main())
