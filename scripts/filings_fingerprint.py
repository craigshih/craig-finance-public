"""
印出「大佬 13F ＋ 川普 278-T」最新申報的指紋，給 workflow 的 gate 判斷要不要重建網站。
只用標準函式庫（gate job 沒有安裝套件），每次只打 11 個很小的請求。
"""

import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEC_UA = os.environ.get("SEC_USER_AGENT") or "craig-finance-hub"


def get(url: str, ua: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main() -> int:
    ciks = [int(c) for c in re.findall(r'^\s*\("\w+", "[^"]+", "[^"]+", (\d+),', (ROOT / "whales.py").read_text(encoding="utf-8"), re.M)]
    parts = []
    for cik in ciks:
        try:
            r = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", SEC_UA)["filings"]["recent"]
            parts.append(next((r["accessionNumber"][i] for i, f in enumerate(r["form"]) if f == "13F-HR"), ""))
        except Exception as exc:  # 檢查失敗就當作「有變動」，寧可多建一次
            print(f"sec {cik}: {exc}", file=sys.stderr)
            parts.append("error")
    try:
        q = urllib.parse.urlencode({"draw": 1, "start": 0, "length": 50, "search[value]": "Trump, Donald", "order[0][column]": 0, "order[0][dir]": "desc"})
        rows = get(f"https://extapps2.oge.gov/201/Presiden.nsf/API.xsp/v3/rest?{q}", "Mozilla/5.0")["data"]
        parts.append(max((r["docDate"] for r in rows if r["name"] == "Trump, Donald J"), default=""))
    except Exception as exc:
        print(f"oge: {exc}", file=sys.stderr)
        parts.append("error")
    print(hashlib.sha1("|".join(parts).encode()).hexdigest()[:16])
    return 0


if __name__ == "__main__":
    sys.exit(main())
