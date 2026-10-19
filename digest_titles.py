"""
每日總經目錄卡的大標題：把當天的新聞標題與重點交給 AI，寫成一句「今天發生什麼事」的摘要標題，
再挑 3～4 個主題標籤。每一天只產生一次，存在 data/digest_titles/{date}.json。
"""

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent
SOURCES_DIR = Path(os.environ.get("SOURCES_DIR", ROOT / "sources"))
DIGEST_DIR = SOURCES_DIR / "tim-lu" / "data" / "digests"
OUT_DIR = ROOT / "data" / "digest_titles"
GROQ_API_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b"

PROMPT = """以下是 {date} 的財經新聞（依來源分組）。請寫出今天的「頭版標題」與主題標籤。

規則：
- headline：一句繁體中文，18～28 個字，點出今天最重要的一到兩個主題，像報紙頭版標題，兩個主題之間用「，」隔開；只能根據下面的新聞，不要編造。
- tags：3～4 個主題標籤，每個 2～6 個字（例如「AI 伺服器」「聯準會」「記憶體」）。
- 不要給任何投資建議。

只輸出 JSON：{{"headline": "...", "tags": ["...", "..."]}}

新聞：
{news}
"""


def first_point(a: dict) -> str:
    for line in (a.get("structured_summary") or "").splitlines():
        line = line.strip().lstrip("-・ ").strip()
        if line and not line.startswith("【"):
            return line
    return ""


def make_title(d: dict) -> dict | None:
    lines = []
    for sec in d.get("news_sections", []):
        lines.append(f"[{sec.get('name')}]")
        for a in sec.get("articles", [])[:8]:
            point = first_point(a)
            lines.append(f"- {a.get('title')}" + (f"：{point[:60]}" if point else ""))
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                      json={"model": GROQ_MODEL, "reasoning_effort": "low", "max_completion_tokens": 800,
                            "response_format": {"type": "json_object"},
                            "messages": [{"role": "user", "content": PROMPT.format(date=d["date"], news="\n".join(lines))}]},
                      timeout=120)
    r.raise_for_status()
    out = json.loads(r.json()["choices"][0]["message"]["content"])
    headline = str(out.get("headline", "")).strip()
    tags = [str(t).strip() for t in out.get("tags", []) if str(t).strip()][:4]
    return {"headline": headline[:34], "tags": tags} if headline else None


def main() -> int:
    if not GROQ_API_KEY:
        print("⚠️ 沒有 GROQ_API_KEY，略過每日摘要標題", file=sys.stderr)
        return 0
    if not DIGEST_DIR.is_dir():
        print(f"⚠️ 找不到 {DIGEST_DIR}", file=sys.stderr)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    made = 0
    for f in sorted(DIGEST_DIR.glob("*.json")):
        out = OUT_DIR / f.name
        if out.exists():
            continue
        try:
            title = make_title(json.loads(f.read_text(encoding="utf-8")))
        except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
            print(f"⚠️ {f.stem} 摘要標題產生失敗：{exc}", file=sys.stderr)
            continue
        if title:
            out.write_text(json.dumps(title, ensure_ascii=False), encoding="utf-8")
            made += 1
    print(f"✅ 每日摘要標題：新增 {made} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
