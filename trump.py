"""
川普的股票交易：美國政府道德辦公室（OGE）公開的總統財產申報 OGE Form 278-T（定期交易報告）。

- 申報清單：OGE 官網用的公開 API（extapps2.oge.gov/201/Presiden.nsf/API.xsp/v3/rest），可以列出每一份 278-T 的 PDF
- 內容：PDF 是掃描檔，用 pypdf 取出文字（有 OCR 雜訊），逐行解析「公司名稱、買／賣、日期、金額區間」
- 公司名稱 → 美股代號：SEC 官方公司代號表（跟 whales.py 同一套正規化）；對不到的照原名顯示，不猜
- 債券（有 % 或 Due 的行）不算；每一筆都能連回 OGE 原始 PDF
- 解析過的申報存在 data/whales/trump/，之後只處理新申報

限制（頁面上會說明）：278-T 只列金額「區間」，不是實際金額；OGE 沒有說明交易是本人決定還是委託帳戶操作；
申報可在交易後最多 45 天才提出。依法，這些資料不得用於商業或募款等用途，本站只做個人研究參考。

另外讀 SEC 上川普本人（CIK 947033）的 Schedule 13D，取得他在川普媒體科技集團（DJT）的持股比例。
"""

import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

import whales

ROOT = Path(__file__).parent
DIR = ROOT / "data" / "whales" / "trump"
OUT = ROOT / "data" / "whales" / "trump.json"
API = "https://extapps2.oge.gov/201/Presiden.nsf/API.xsp/v3/rest"
UA = "Mozilla/5.0 (compatible; craig-finance-hub/1.0; +https://github.com/craigshih)"
TAIPEI = timezone(timedelta(hours=8))
TRUMP_CIK = 947033
BRACKETS = [1_000, 15_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 5_000_000, 25_000_000, 50_000_000]
LINE = re.compile(
    r"^\s*\S{1,4}\s+(?P<name>.+?)\s+(?P<type>\S{0,3}\s?(?:\S*rcha\S*|\S*urch\S*|[|lIJ1]?\s?s[aeo][lti1]\S{0,2}|sold|exchange))\s+"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+(?:Y\s?[eo]\s?s|N\s?o|Y|N)\s+(?P<amt>.+)$", re.I)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def filings() -> list[dict]:
    r = requests.get(API, timeout=60, headers={"User-Agent": UA}, params={
        "draw": 1, "start": 0, "length": 200, "search[value]": "Trump, Donald", "order[0][column]": 0, "order[0][dir]": "desc"})
    r.raise_for_status()
    out = []
    for row in r.json()["data"]:
        if row["name"] != "Trump, Donald J" or "278 Transaction" not in row["type"]:
            continue
        m = re.search(r"href='([^']+)'", row["type"])
        if m:
            url = m.group(1).replace(" ", "%20")
            out.append({"url": url, "posted": row["docDate"][:10], "id": re.search(r"PAS\+Index/([0-9A-F]+)/", url).group(1)})
    return sorted(out, key=lambda f: f["posted"])


def snap(v: float) -> int:
    return min(BRACKETS, key=lambda b: abs(b - v))


def amount(raw: str) -> tuple[int, int] | None:
    """金額區間，例如「$1 001 • $15 000」「S1,001-$15000」；OCR 常把 $ 認成 S、逗號認成句點。"""
    raw = raw.strip()
    groups = [re.sub(r"[^\d]", "", g) for g in re.findall(r"\d[\d,. ]*\d|\d", raw)]
    nums = [float(g) for g in groups if g]
    if raw.lower().startswith("over") and nums:
        return (snap(nums[0]), snap(nums[0]))
    if len(nums) < 2:
        return None
    lo, hi = snap(nums[0]), snap(nums[1])
    return (lo, hi) if lo < hi else None


DATE = r"(\d{1,2}\s?/\s?\d{1,2}\s?/\s?\d\s?\d\s?\d\s?\d)"
RIGHT = re.compile(r"^\s*" + DATE + r"\s+(?:Y\s?[eo]\s?s|N\s?o|Y|N)\s+(.+)$", re.I)
LEFT = re.compile(r"^\s*[I|]?\s*(\d{1,4})\s+(.+?)\s*$")
TYPE = re.compile(r"\s(\S*(?:rch|urc)\S*|[|lIJ1]?\s?[s5][aeo\'][lti1]\S{0,2}|[s5][aeo]\S{0,2}|sold|exchange)\s*\.?$", re.I)


def _row(name: str, typ: str, d: str, amt: str) -> dict | None:
    t = typ.lower()
    side = "exchange" if "exch" in t else "buy" if ("rch" in t or "urc" in t) else "sell"
    try:
        iso = datetime.strptime(re.sub(r"\s", "", d), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None
    a = amount(amt)
    return {"name": " ".join(name.split()), "side": side, "date": iso, "lo": a[0] if a else None, "hi": a[1] if a else None}


def parse(text: str) -> list[dict]:
    """兩種版面：同一行（名稱 類型 日期 金額）；或分兩欄（先列全部名稱，再列全部日期金額）。
    分欄時依序配對，數量對不上就整頁放棄，寧可少也不要配錯。"""
    rows, lefts, rights = [], [], []
    for line in text.splitlines():
        if "%" in line or re.search(r"\bDue\b", line):
            continue  # 債券
        m = LINE.match(line)
        if m:
            r = _row(m.group("name"), m.group("type"), m.group("date"), m.group("amt"))
            if r:
                rows.append(r)
            continue
        rm = RIGHT.match(line)
        if rm:
            rights.append((rm.group(1), rm.group(2)))
            continue
        lm = LEFT.match(line)
        if lm and not re.search(r"\d/\d", line):
            tm = TYPE.search(" " + lm.group(2))
            lefts.append((lm.group(2)[: tm.start()].strip(), tm.group(1)) if tm else None)
    if lefts and len(lefts) == len(rights):
        for left, (d, amt) in zip(lefts, rights):
            if left:
                r = _row(left[0], left[1], d, amt)
                if r:
                    rows.append(r)
    return rows


def parse_filing(f: dict) -> list[dict]:
    cache = DIR / f"{f['id']}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import io

    import pypdf
    log(f"下載 {f['url'].rsplit('/', 1)[-1]}")
    pdf = requests.get(f["url"], timeout=900, headers={"User-Agent": UA}).content
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    rows, total = [], 0
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        for r in parse(text):
            rows.append({**r, "page": i})
        for n in re.findall(r"(?m)^\s*[I|]?\s*(\d{1,4})\s+[A-Za-z]", text):
            total = max(total, int(n))
    if total == 0 and len(reader.pages) > 2:
        # 純圖片的掃描檔（沒有文字層）：用 tesseract OCR（GitHub 建站時會安裝；本機沒有就先跳過、不寫快取）
        ocr = ocr_pages(pdf)
        if ocr is None:
            log("  沒有文字層、這台機器也沒有 OCR，下次在 GitHub 建站時處理")
            return {"total": 0, "rows": []}
        for i, text in enumerate(ocr, 1):
            for r in parse(text):
                rows.append({**r, "page": i})
            # OCR 會把序號讀錯，總筆數改數「有交易日期的行」
            total += len(re.findall(r"\d{1,2}\s?/\s?\d{1,2}\s?/\s?20\d\d", text))
    data = {"total": total, "rows": rows}
    DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    log(f"  {len(reader.pages)} 頁、申報 {total} 筆（含債券）、解析出 {len(rows)} 筆股票交易")
    return data


def ocr_pages(pdf: bytes) -> list[str] | None:
    import shutil
    import subprocess
    import tempfile
    if not (shutil.which("pdftoppm") and shutil.which("tesseract")):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.pdf"
        src.write_bytes(pdf)
        subprocess.run(["pdftoppm", "-r", "200", "-gray", "-png", str(src), f"{tmp}/p"], check=True)
        imgs = sorted(Path(tmp).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        # 先試第 3 頁，看哪種版面模式能把「名稱 類型 日期 金額」讀在同一行
        best, best_n = "6", -1
        for psm in ("6", "4", "3"):
            sample = subprocess.run(["tesseract", str(imgs[min(2, len(imgs) - 1)]), "-", "--psm", psm], capture_output=True, text=True).stdout
            n = len(parse(sample))
            log(f"  OCR psm {psm}：第 3 頁解析出 {n} 筆；前幾行：{sample.splitlines()[8:14]}")
            if n > best_n:
                best, best_n = psm, n
        texts = []
        for img in imgs:
            out = subprocess.run(["tesseract", str(img), "-", "--psm", best], capture_output=True, text=True)
            texts.append(out.stdout)
        return texts


def ticker_index() -> tuple[dict, dict]:
    names = whales.sec_name_tickers()
    collapsed = {k.replace(" ", ""): v for k, v in names.items()}
    return names, collapsed


def official_names() -> dict[str, str]:
    """代號 → SEC 登記的公司名稱（顯示用，取代 OCR 讀出來的名稱）。"""
    data = whales.sec_get("https://www.sec.gov/files/company_tickers.json").json()
    out: dict[str, str] = {}
    for row in data.values():
        out.setdefault(row["ticker"], row["title"])
    return out


FUND = re.compile(r"\b(ISHARES|SPDR|VANGUARD|FIDELITY|STATE STREET|INVESCO|SCHWAB|ETF|FUND|INDEX|TRUST|TR|BOND|TREAS\w*|MSCI|RUSSELL|S&P 500)\b", re.I)
OCR_FIX = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "!": "I", "|": "I", "$": "S"})


def to_ticker(name: str, names: dict, collapsed: dict) -> str | None:
    """先用原名比；比不到再把 OCR 常見的數字／字母混淆（0→O、2→Z、5→S…）修正後再比一次。ETF、基金不算股票。"""
    if FUND.search(name):
        return None
    hit = _match(name, names, collapsed)
    return hit or _match(name.translate(OCR_FIX), names, collapsed)


def _match(name: str, names: dict, collapsed: dict) -> str | None:
    words = whales.norm(name).split()
    for cut in range(0, 3):
        key = " ".join(words[:len(words) - cut]) if cut else " ".join(words)
        if len(key) >= 3:
            if key in names:
                return names[key]
            if key.replace(" ", "") in collapsed:  # OCR 把字切開，例如 EXXONMOB IL
                return collapsed[key.replace(" ", "")]
    return None


def djt_stake() -> dict | None:
    """川普本人在 SEC 的最新 Schedule 13D（川普媒體科技集團 DJT）。"""
    try:
        d = whales.sec_get(f"https://data.sec.gov/submissions/CIK{TRUMP_CIK:010d}.json").json()
    except Exception as exc:
        log(f"⚠️ 讀不到川普的 SEC 申報：{exc}")
        return None
    r = d["filings"]["recent"]
    for i, form in enumerate(r["form"]):
        if "13D" not in form:
            continue
        acc = r["accessionNumber"][i]
        folder = f"https://www.sec.gov/Archives/edgar/data/{TRUMP_CIK}/{acc.replace('-', '')}"
        out = {"form": form, "filed": r["filingDate"][i], "url": f"{folder}/", "issuer": None}
        try:
            doc = whales.sec_get(f"{folder}/primary_doc.xml").text  # 新版 13D 是結構化 XML
            pct = re.search(r"<(?:\w+:)?percentOfClass>\s*([\d.]+)", doc) or re.search(r"Percent of class[^0-9]{0,200}?([\d.]+)\s*%", doc, re.I | re.S)
            shares = re.search(r"<(?:\w+:)?aggregateAmountOwned>\s*([\d.,]+)", doc)
            out["percent"] = float(pct.group(1)) if pct else None
            out["shares"] = float(shares.group(1).replace(",", "")) if shares else None
            issuer = re.search(r"<(?:\w+:)?issuerName>\s*([^<]+)", doc)
            out["issuer"] = issuer.group(1).replace("&amp;", "&").strip() if issuer else None
        except Exception as exc:
            log(f"⚠️ 13D 內容解析失敗：{exc}")
        return out
    return None


def main() -> int:
    try:
        fs = filings()
    except (requests.RequestException, ValueError, KeyError) as exc:
        log(f"⚠️ OGE 申報清單讀取失敗：{exc}")
        return 0
    names, collapsed = ticker_index()
    trades, stats = [], []
    for f in fs:
        try:
            data = parse_filing(f)
        except Exception as exc:
            log(f"⚠️ {f['url']} 解析失敗：{exc}")
            continue
        stats.append({"url": f["url"], "posted": f["posted"], "total": data["total"], "parsed": len(data["rows"]),
                      "first": min((r["date"] for r in data["rows"]), default=None), "last": max((r["date"] for r in data["rows"]), default=None)})
        for r in data["rows"]:
            if not ("2024-11-01" <= r["date"] <= f["posted"]):
                continue  # OCR 把日期認錯（例如未來日期）就丟掉
            trades.append({**r, "ticker": to_ticker(r["name"], names, collapsed), "url": f"{f['url']}#page={r['page']}", "posted": f["posted"]})
        time.sleep(1)

    cutoff = (date.today() - timedelta(days=120)).isoformat()
    by: dict[str, dict] = {}
    for t in trades:
        if t["date"] < cutoff or t["side"] == "exchange":
            continue
        key = t["ticker"] or t["name"]
        a = by.setdefault(key, {"ticker": t["ticker"], "name": t["name"], "buys": 0, "sells": 0, "buy_lo": 0, "buy_hi": 0,
                                "sell_lo": 0, "sell_hi": 0, "last": t["date"], "url": t["url"]})
        side = "buy" if t["side"] == "buy" else "sell"
        a[f"{side}s"] += 1
        a[f"{side}_lo"] += t["lo"] or 0
        a[f"{side}_hi"] += t["hi"] or 0
        if t["date"] >= a["last"]:
            a["last"], a["url"] = t["date"], t["url"]
    titles = official_names()
    for a in by.values():
        if a["ticker"] in titles:
            a["name"] = titles[a["ticker"]]
    # 只列對到股票代號的（OCR 雜訊太多、對不到的不顯示，避免錯誤名稱）；依交易筆數排序，金額區間只當參考
    rows = sorted((a for a in by.values() if a["ticker"]), key=lambda a: -(a["buys"] - a["sells"]))
    latest = max((t["date"] for t in trades), default=None)
    out = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
        "filings": stats, "latest_trade": latest, "since": cutoff,
        "n_trades": sum(1 for t in trades if t["date"] >= cutoff), "matched": sum(1 for t in trades if t["date"] >= cutoff and t["ticker"]),
        "net_buys": [a for a in rows if a["buys"] > a["sells"]][:25],
        "net_sells": sorted((a for a in rows if a["sells"] > a["buys"]), key=lambda a: -(a["sells"] - a["buys"]))[:25],
        "by_ticker": {a["ticker"]: a for a in rows if a["ticker"]},
        "djt": djt_stake(),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    log(f"✅ 川普 278-T：{len(fs)} 份申報、近 120 天 {out['n_trades']} 筆股票交易（對到代號 {out['matched']} 筆）、最新交易日 {latest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
