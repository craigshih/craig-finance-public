"""
每日一檔：每天挑一檔台股，用「科技新報短影音」那種好讀的方式介紹：
提問式標題 → 一句話看懂 → 發展歷史 → 產業位置 → 最近在做什麼 → 未來前景（機會與風險）→ 名詞小辭典 → 資料來源。

挑選（不使用站長持股，避免從推薦反推持股）：
  候選＝供應鏈地圖台廠 ∪ 每週研究候選 ∪ 成交值前 150 名（不含 ETF），60 天內推薦過的不再選；
  分數＝今天早上每日總經（鉅亨網＋工商時報）點名次數 × 3 ＋ 近 7 天鉅亨網新聞篇數 ＋ 研究候選／供應鏈加分。
內容只能用這些資料（AI 不准自己補數字）：
  證交所／櫃買公司基本資料（成立、上市日期、董事長…）、中文維基百科簡介、鉅亨網新聞、供應鏈地圖（有出處的關係）、
  月營收、毛利率、本益比、殖利率、法人籌碼。寫完後含有「資料裡沒有的數字」的句子一律刪掉。
輸出 data/daily_pick/{date}.json；SEND=1 時把同一份內容寄到 MAIL_TO（Gmail SMTP）。
這是研究素材，不是買賣建議。
"""

import html
import json
import os
import re
import smtplib
import sys
import time
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).parent
OUT_DIR = ROOT / "data" / "daily_pick"
SOURCES_DIR = Path(os.environ.get("SOURCES_DIR", ROOT / "sources"))
DIGEST_DIR = SOURCES_DIR / "tim-lu" / "data" / "digests"
TAIPEI = timezone(timedelta(hours=8))
UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "openai/gpt-oss-120b"
SITE = "https://craig-finance.pages.dev"
REPEAT_DAYS = 60
TOP_N = 150
WIKI = "https://zh.wikipedia.org"

BANNED = ["買進", "賣出", "加碼", "減碼", "目標價", "進場", "出場", "停損", "停利", "抄底", "必漲", "穩賺", "推薦買"]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def get(url: str, **kw):
    for attempt in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=40, **kw)
            if r.status_code == 200:
                return r
            log(f"⚠️ {url} 回 {r.status_code}")
        except requests.RequestException as exc:
            log(f"⚠️ {url}：{exc}")
        time.sleep(3 * (attempt + 1))
    return None


# ---------------------------------------------------------------- 挑選

def recent_codes() -> set[str]:
    cutoff = (datetime.now(TAIPEI).date() - timedelta(days=REPEAT_DAYS)).isoformat()
    out = set()
    for f in OUT_DIR.glob("*.json"):
        if f.stem >= cutoff:
            try:
                out.add(json.loads(f.read_text(encoding="utf-8"))["code"])
            except (json.JSONDecodeError, KeyError, OSError):
                pass
    return out


def today_digest_text(today: str) -> str:
    f = DIGEST_DIR / f"{today}.json"
    if not f.exists():
        return ""
    d = json.loads(f.read_text(encoding="utf-8"))
    parts = []
    for sec in d.get("news_sections", []):
        for a in sec.get("articles", []):
            parts += [a.get("title") or "", a.get("structured_summary") or ""]
    return "\n".join(parts)


def short(name: str) -> str:
    return re.sub(r"-KY$|-創$|\*", "", name or "").strip()


def cnyes_news(name: str, limit: int = 20) -> list[dict]:
    r = get(f"https://ess.api.cnyes.com/ess/api/v1/news/keyword?q={quote(name)}&limit={limit}&page=1")
    if not r:
        return []
    out = []
    for it in ((r.json().get("data") or {}).get("items") or []):
        if it.get("objectType") not in (None, "NEWS"):
            continue
        title = re.sub(r"</?mark>", "", it.get("title") or "")
        if not title:
            continue
        out.append({"title": html.unescape(title), "url": f"https://news.cnyes.com/news/id/{it['newsId']}",
                    "date": datetime.fromtimestamp(it.get("publishAt") or 0, TAIPEI).strftime("%Y-%m-%d"),
                    "summary": html.unescape(re.sub(r"</?mark>", "", it.get("summary") or ""))[:300]})
    return out


def choose(stocks: dict, weekly: dict, today: str) -> tuple[str, dict]:
    from supply_map import ALL_TW

    skip = recent_codes()
    top = sorted((s for s in stocks.values() if s.get("trade_value") and re.fullmatch(r"[1-9]\d{3}", s["code"])),
                 key=lambda s: -s["trade_value"])[:TOP_N]
    cands = {c for c in [*ALL_TW, *weekly, *(s["code"] for s in top)] if c in stocks and re.fullmatch(r"[1-9]\d{3}", c)} - skip
    digest = today_digest_text(today)
    rank = {s["code"]: i for i, s in enumerate(top)}
    pre = []
    for c in cands:
        n = short(stocks[c]["name"])
        mentions = digest.count(n) if len(n) >= 2 else 0
        score = mentions * 3 + (2 if c in weekly else 0) + (1 if c in ALL_TW else 0) + (1 - rank.get(c, TOP_N) / TOP_N)
        pre.append((score, mentions, c))
    pre.sort(reverse=True)
    week_ago = (datetime.now(TAIPEI).date() - timedelta(days=7)).isoformat()
    best = None
    for score, mentions, c in pre[:20]:  # 只對前 20 名查新聞，對鉅亨網客氣一點
        news = cnyes_news(short(stocks[c]["name"]))
        fresh = [n for n in news if n["date"] >= week_ago and short(stocks[c]["name"]) in n["title"]]
        total = score + min(len(fresh), 10)
        log(f"  候選 {c} {stocks[c]['name']}：早報點名 {mentions}、近 7 天新聞 {len(fresh)} → {total:.1f}")
        if best is None or total > best[0]:
            best = (total, c, {"news": news, "mentions": mentions, "fresh": len(fresh)})
        time.sleep(1)
    if not best:
        raise RuntimeError("沒有可以推薦的候選")
    return best[1], best[2]


# ---------------------------------------------------------------- 資料

def profile(code: str) -> dict | None:
    for url, key in (("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "公司代號"),
                     ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", "SecuritiesCompanyCode")):
        r = get(url)
        if not r:
            continue
        for x in r.json():
            if x.get(key) != code:
                continue
            g = lambda *ks: next((str(x[k]).strip() for k in ks if x.get(k) not in (None, "")), None)
            ymd = lambda s: f"{s[:4]}-{s[4:6]}-{s[6:8]}" if s and re.fullmatch(r"\d{8}", s) else s
            return {"全名": g("公司名稱", "CompanyName"), "董事長": g("董事長", "Chairman"), "總經理": g("總經理", "GeneralManager"),
                    "成立日期": ymd(g("成立日期", "DateOfIncorporation")), "上市櫃日期": ymd(g("上市日期", "DateOfListing")),
                    "實收資本額（元）": g("實收資本額", "Paidin.Capital.NTDollars"), "地址": g("住址", "Address"),
                    "網址": g("網址", "WebAddress"), "英文簡稱": g("英文簡稱", "Symbol"),
                    "source": url}
    return None


def wiki_summary(name: str, full: str | None) -> dict | None:
    """中文維基百科的簡介（台灣正體）。先找標題含公司名的條目。"""
    for q in [full, f"{name} 公司", name]:
        if not q:
            continue
        r = get(f"{WIKI}/w/api.php", params={"action": "query", "list": "search", "srsearch": q, "format": "json", "srlimit": 5})
        if not r:
            continue
        for hit in r.json().get("query", {}).get("search", []):
            title = hit["title"]
            if name not in title and (not full or full[:4] not in title):
                continue
            ex = get(f"{WIKI}/w/api.php", params={"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "plain",
                                                   "titles": title, "variant": "zh-tw", "redirects": 1, "format": "json"})
            if not ex:
                continue
            page = next(iter(ex.json().get("query", {}).get("pages", {}).values()), {})
            text = (page.get("extract") or "").strip()
            if len(text) < 80:
                continue
            return {"title": page.get("title", title), "url": f"{WIKI}/zh-tw/{quote(page.get('title', title))}", "text": text[:6000]}
    return None


def wiki_link(term: str) -> str | None:
    """名詞對應的維基百科條目：先找同名條目，再用搜尋找標題相近的；都沒有就回 None。"""
    r = get(f"{WIKI}/w/api.php", params={"action": "query", "titles": term, "redirects": 1, "variant": "zh-tw", "format": "json"})
    if r:
        page = next(iter(r.json().get("query", {}).get("pages", {}).values()), {})
        if page.get("title") and "missing" not in page and "invalid" not in page:
            return f"{WIKI}/zh-tw/{quote(page['title'])}"
    r = get(f"{WIKI}/w/api.php", params={"action": "query", "list": "search", "srsearch": term, "srlimit": 3, "format": "json"})
    norm = lambda x: re.sub(r"[\s‑\-－_]", "", x).lower()
    for hit in (r.json().get("query", {}).get("search", []) if r else []):
        t = hit["title"]
        if norm(term) in norm(t) or norm(t) in norm(term):
            return f"{WIKI}/zh-tw/{quote(t)}"
    return None


# ---------------------------------------------------------------- AI 撰寫

PROMPT = """你是財經科普短影音的編劇，風格像「科技新報」的短影音：開頭一個讓人想點進來的問題，接著用說故事的方式，
從公司怎麼起家、在產業裡扮演什麼角色，一路講到最近在做什麼、未來可能的機會與風險。讀者是一般投資新手。

嚴格規則：
1. 只能使用 DATA 裡的事實。年份、日期、金額、百分比、人名、客戶名一律要能在 DATA 找到；DATA 沒有的就不要寫，寧可寫得少。
2. 不給任何買賣建議：不要出現「買進、賣出、加碼、減碼、目標價、進場、出場、停損、必漲」等字眼，也不要預測股價。
3. 維基百科（wiki）是公司沿革的主要來源；新聞（news）是「最近在做什麼」的主要來源；供應鏈關係只能用 supply 裡有出處的。
4. 新聞標題裡的「點」「關卡」「台股開盤／收盤」講的是大盤加權指數，不是這家公司的股價；不要把大盤的漲跌、點數寫成公司股價。
   也不要寫股價走勢，重點放在公司本身的事業。
5. 用台灣用語、正體中文，句子短、口語、好讀。專有名詞第一次出現時用白話解釋，並放進 terms。
6. 輸出 JSON，格式：
{
  "title": "提問式標題，30 字內，例如「大立光豪砸幾十億，就為了台積電？」",
  "one_liner": "一句話看懂這家公司（40 字內）",
  "history": [{"when": "年份或時期（DATA 裡有的）", "what": "那時發生什麼（50 字內）"}],   // 3～6 個，從創立到現在
  "industry": "它在產業裡的位置：做什麼產品、上下游是誰、主要客戶或競爭對手（150 字內）",
  "now": ["最近在做什麼（每點 60 字內，根據 news，2～4 點）"],
  "opportunities": ["未來可能的成長機會（每點 50 字內，2～3 點）"],
  "risks": ["需要注意的風險（每點 50 字內，2～3 點）"],
  "watch": ["之後可以追蹤的指標或事件（每點 40 字內，2～3 點，例如月營收、法說會、某項新產品進度）"],
  "terms": [{"term": "專有名詞", "plain": "白話解釋（60 字內）"}]   // 3～6 個
}

DATA:
"""


class TooLarge(Exception):
    pass


def call_groq(prompt: str) -> dict:
    for attempt in range(4):
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                          json={"model": GROQ_MODEL, "messages": [{"role": "user", "content": prompt}],
                                "max_completion_tokens": 2800, "reasoning_effort": "low", "temperature": 0.4,
                                "response_format": {"type": "json_object"}}, timeout=180)
        # Groq 免費額度每分鐘 8000 token，「輸入＋預留輸出」超過就回 413／429 Request too large：要縮短輸入，重試沒用
        if r.status_code == 413 or (r.status_code == 429 and "too large" in r.text.lower()):
            raise TooLarge(r.text[:200])
        if r.status_code == 429:
            time.sleep(20 * (attempt + 1))
            continue
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])
    raise RuntimeError("Groq 一直回 429")


def write_story(data: dict) -> tuple[dict, str]:
    """資料太長就逐步縮短維基百科與新聞摘要再試，直到放得進 Groq 的單次上限。"""
    wiki, news = data.get("wiki") or "", data["news"]
    for wiki_len, n_news, sum_len in ((2400, 8, 120), (1500, 6, 80), (900, 4, 0)):
        d = {**data, "wiki": wiki[:wiki_len] or None,
             "news": [{**n, "summary": n["summary"][:sum_len]} if sum_len else {k: n[k] for k in ("date", "title")} for n in news[:n_news]]}
        ctx = json.dumps(d, ensure_ascii=False)
        try:
            return call_groq(PROMPT + ctx), ctx
        except TooLarge:
            log(f"  資料太長（{len(ctx)} 字），縮短後重試")
            time.sleep(15)
    raise RuntimeError("資料縮到最短仍超過 AI 單次上限")


NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    out = set()
    for m in NUM.findall(text):
        v = m.replace(",", "")
        out.add(v)
        if "." in v:
            out.add(v.rstrip("0").rstrip("."))
    return out


def allowed_numbers(ctx_text: str) -> set[str]:
    nums = numbers_in(ctx_text)
    # 民國年 ↔ 西元年、百分比四捨五入到整數與一位小數
    extra = set()
    for v in list(nums):
        try:
            f = float(v)
        except ValueError:
            continue
        extra |= {str(round(f)), f"{f:.1f}", f"{round(f, 1):g}"}
        if 60 <= f <= 130 and f.is_integer():
            extra.add(str(int(f) + 1911))
    return nums | extra | {str(i) for i in range(0, 13)}  # 小數字（「三大」「第 2 季」）放行


def scrub(text: str, allowed: set[str]) -> tuple[str, int]:
    """刪掉含有 DATA 裡沒有的數字、或含交易用語的句子；回傳（清過的文字, 刪掉幾句）。"""
    parts = re.split(r"(?<=[。！？；])", text or "")
    kept, dropped = [], 0
    for p in parts:
        bad_num = any(n not in allowed for n in numbers_in(p))
        if bad_num or any(w in p for w in BANNED):
            dropped += 1
            continue
        kept.append(p)
    return "".join(kept).strip(), dropped


def clean_story(raw: dict, allowed: set[str]) -> tuple[dict, int]:
    dropped = 0

    def s(x):
        nonlocal dropped
        t, d = scrub(str(x or "").replace("\u2011", "-").replace("\u2010", "-"), allowed)  # AI 常寫不換行連字號，維基搜尋會找不到
        dropped += d
        return t

    out = {"title": s(raw.get("title")), "one_liner": s(raw.get("one_liner")), "industry": s(raw.get("industry"))}
    out["history"] = [h for h in ({"when": s(x.get("when")), "what": s(x.get("what"))} for x in raw.get("history") or [] if isinstance(x, dict))
                      if h["when"] and h["what"]]
    for k in ("now", "opportunities", "risks", "watch"):
        out[k] = [t for t in (s(x) for x in raw.get(k) or []) if t]
    out["terms"] = [{"term": str(t.get("term", "")).replace("\u2011", "-").replace("\u2010", "-")[:20], "plain": s(t.get("plain"))}
                    for t in raw.get("terms") or [] if isinstance(t, dict) and t.get("term")]
    return out, dropped


# ---------------------------------------------------------------- email

def email_html(p: dict) -> str:
    e = lambda x: html.escape(str(x or ""))
    st = p["story"]
    li = lambda xs: "".join(f'<li style="margin:0 0 6px">{e(x)}</li>' for x in xs)
    sec = lambda title, body: (f'<h3 style="margin:22px 0 8px;font-size:16px;color:#c0392b">{title}</h3>{body}' if body else "")
    hist = "".join(f'<tr><td style="padding:4px 10px 4px 0;color:#c99400;font-weight:700;white-space:nowrap;vertical-align:top">{e(h["when"])}</td>'
                   f'<td style="padding:4px 0">{e(h["what"])}</td></tr>' for h in st["history"])
    terms = "".join(f'<li style="margin:0 0 8px"><b>{e(t["term"])}</b>：{e(t["plain"])}'
                    + (f' <a href="{e(t["url"])}" style="color:#2563eb">（資料來源）</a>' if t.get("url") else "") + "</li>" for t in st["terms"])
    src = "".join(f'<li style="margin:0 0 4px"><a href="{e(s["url"])}" style="color:#2563eb">{e(s["label"])}</a></li>' for s in p["sources"])
    k = p.get("snapshot") or {}
    snap = "・".join(x for x in [
        f'收盤 {k["close"]:,}' if k.get("close") else "", f'月營收年增 {k["rev_yoy"]}%' if k.get("rev_yoy") is not None else "",
        f'毛利率 {k["gross"]}%' if k.get("gross") is not None else "", f'本益比 {k["pe"]}' if k.get("pe") else "",
        f'殖利率 {k["yield"]}%' if k.get("yield") else ""] if x)
    return f"""<div style="max-width:640px;margin:0 auto;font-family:-apple-system,'PingFang TC','Noto Sans TC',sans-serif;color:#1f2937;line-height:1.75;font-size:15px">
<p style="margin:0;color:#c99400;font-weight:700;letter-spacing:.08em">CRAIG 財經站・每日一檔・{e(p['date'])}</p>
<h1 style="margin:6px 0 4px;font-size:24px;line-height:1.35">{e(st['title'])}</h1>
<p style="margin:0 0 4px;font-size:17px"><b>{e(p['name'])}</b>（{e(p['code'])}・{e(p['market'])}・{e(p.get('industry') or '')}）</p>
<p style="margin:0 0 12px;color:#4b5563">{e(st['one_liner'])}</p>
{f'<p style="margin:0 0 8px;font-size:13px;color:#6b7280">{e(snap)}</p>' if snap else ''}
{sec('發展歷史', f'<table style="border-collapse:collapse">{hist}</table>' if hist else '')}
{sec('產業位置', f'<p style="margin:0">{e(st["industry"])}</p>' if st['industry'] else '')}
{sec('最近在做什麼', f'<ul style="padding-left:20px;margin:0">{li(st["now"])}</ul>' if st['now'] else '')}
{sec('未來的機會', f'<ul style="padding-left:20px;margin:0">{li(st["opportunities"])}</ul>' if st['opportunities'] else '')}
{sec('需要注意的風險', f'<ul style="padding-left:20px;margin:0">{li(st["risks"])}</ul>' if st['risks'] else '')}
{sec('之後可以追蹤', f'<ul style="padding-left:20px;margin:0">{li(st["watch"])}</ul>' if st['watch'] else '')}
{sec('名詞小辭典', f'<ul style="padding-left:20px;margin:0">{terms}</ul>' if terms else '')}
{sec('資料來源', f'<ul style="padding-left:20px;margin:0;font-size:13px">{src}</ul>')}
<p style="margin:22px 0 0;font-size:13px"><a href="{SITE}/pick/{e(p['date'])}.html" style="color:#c0392b;font-weight:700">在網站上看（含術語註解）→</a></p>
<p style="margin:16px 0 0;font-size:12px;color:#9ca3af">本文由 AI 依公開資料整理，僅供學習研究，不構成任何投資建議；內容可能有誤，請以原始資料為準。投資有風險，請自行判斷並承擔責任。</p>
</div>"""


def send_email(p: dict) -> bool:
    user, pw = os.environ.get("GMAIL_ADDRESS"), os.environ.get("GMAIL_APP_PASSWORD")
    to = os.environ.get("MAIL_TO") or user
    if not (user and pw and to):
        log("⚠️ 沒有設定 GMAIL_ADDRESS／GMAIL_APP_PASSWORD，不寄信")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"每日一檔｜{p['name']}（{p['code']}）：{p['story']['title']}"
    msg["From"], msg["To"] = user, to
    text = f"{p['story']['title']}\n{p['name']}（{p['code']}）\n{p['story']['one_liner']}\n\n{SITE}/pick/{p['date']}.html"
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(email_html(p), "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(user, pw)
        s.sendmail(user, [x.strip() for x in to.split(",")], msg.as_string())
    log(f"📧 已寄到 {to}")
    return True


# ---------------------------------------------------------------- LINE

WEEK = "一二三四五六日"
LINE_MAX = 5000


def line_messages(p: dict) -> list[str]:
    """LINE 群組用的純文字：第 1 則是主要內容，第 2 則是名詞小辭典與資料來源（一次推播送出，只算 1 則額度）。"""
    st, k = p["story"], p.get("snapshot") or {}
    d = datetime.fromisoformat(p["date"])
    dot = lambda xs: "\n".join(f"・{x}" for x in xs)
    snap = "・".join(x for x in [
        f'收盤 {k["close"]:,}' if k.get("close") else "",
        f'月營收年增 {k["rev_yoy"]:+.1f}%' if k.get("rev_yoy") is not None else "",
        f'毛利率 {k["gross"]:.1f}%' if k.get("gross") is not None else "",
        f'本益比 {k["pe"]:.1f}' if k.get("pe") else "", f'殖利率 {k["yield"]:.2f}%' if k.get("yield") else ""] if x)
    parts = [f"📈 每日一檔｜{d.month}/{d.day}（{WEEK[d.weekday()]}）", f"{p['name']}（{p['code']}・{p.get('industry') or p['market']}）",
             f"「{st['title']}」", "", f"💡 一句話看懂\n{st['one_liner']}"]
    if snap:
        parts += ["", f"📊 數字快照\n{snap}"]
    if st["history"]:
        parts += ["", "🏛 發展歷史\n" + "\n".join(f"・{h['when']}｜{h['what']}" for h in st["history"])]
    for icon, title, key in (("🏭", "產業位置", "industry"), ("📰", "最近在做什麼", "now"), ("🚀", "未來的機會", "opportunities"),
                             ("⚠️", "需要注意的風險", "risks"), ("👀", "之後可以追蹤", "watch")):
        v = st.get(key)
        if v:
            parts += ["", f"{icon} {title}\n" + (v if isinstance(v, str) else dot(v))]
    first = "\n".join(parts)[:LINE_MAX]

    second = []
    if st["terms"]:
        second.append("📖 名詞小辭典\n" + "\n".join(f"・{t['term']}：{t['plain']}\n  {t['url']}" for t in st["terms"]))
    if p.get("sources"):
        second.append("🔗 資料來源\n" + "\n".join(f"{i}. {x['label']}\n   {x['url']}" for i, x in enumerate(p["sources"][:6], 1)))
    second.append("※ 本文由 AI 依公開資料整理，僅供學習研究，不構成任何投資建議；內容可能有誤，請以原始資料為準。")
    text2 = "\n\n".join(second)
    if len(text2) > LINE_MAX:  # 太長就少列幾個來源
        text2 = text2[:LINE_MAX - 3] + "…"
    return [first, text2]


def send_line(p: dict) -> bool:
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    groups = [g for g in (os.environ.get("LINE_GROUP_IDS") or "").split(",") if g.strip()]
    if not token or not groups:
        log("⚠️ 沒有 LINE_CHANNEL_ACCESS_TOKEN 或還沒有開通的群組，不推 LINE")
        return False
    msgs = [{"type": "text", "text": t} for t in line_messages(p)]
    ok = True
    for g in groups:
        r = requests.post("https://api.line.me/v2/bot/message/push", timeout=30,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                   "X-Line-Retry-Key": __import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, f"{p['date']}-{g}").__str__()},
                          json={"to": g.strip(), "messages": msgs})
        if r.status_code in (200, 409):  # 409＝同一個 retry key 已經送過，不會重複
            log(f"💬 已推到 LINE 群組 {g[:6]}…")
        else:
            ok = False
            log(f"⚠️ LINE 推播失敗 {r.status_code}：{r.text[:200]}")
    return ok


# ---------------------------------------------------------------- 主程式

def generate(today: str) -> dict:
    import advisor
    from supply_map import LEADERS, SOURCES, TW_MAP, TW_PEERS

    stocks = advisor.market_data()
    if len(stocks) < 1000:
        raise RuntimeError(f"全市場資料只有 {len(stocks)} 檔")
    _, weekly = advisor.weekly_screen()
    code, why = choose(stocks, weekly, today)
    s = stocks[code]
    name = short(s["name"])
    log(f"✅ 今天選：{code} {s['name']}")

    prof = profile(code)
    wiki = wiki_summary(name, (prof or {}).get("全名"))
    news = [n for n in why["news"] if name in n["title"]][:10] or why["news"][:6]
    links = TW_MAP.get(code, {}).get("links", {})
    supply = [{"leader": LEADERS[ld][0], "relation": rel, "note": note,
               "source": dict(zip(("publisher", "date", "title", "url"), SOURCES[src][:4]))}
              for ld, (rel, note, src) in links.items() if src in SOURCES and rel != "同業"]
    peers = [p["name"] for p in TW_PEERS.get(code, [])][:6]
    data = {
        "company": {"code": code, "name": s["name"], "market": s["market"], "industry": s.get("industry"), **(prof or {})},
        "wiki": wiki["text"] if wiki else None,
        "market_data": {k: s.get(k) for k in ("close", "revenue", "margins", "valuation", "flows")},
        "weekly_screen": weekly.get(code),
        "supply": supply, "peers": peers,
        "news": [{k: n[k] for k in ("date", "title", "summary")} for n in news],
    }
    data["company"].pop("source", None)
    raw, ctx = write_story(data)
    story, dropped = clean_story(raw, allowed_numbers(ctx))
    if not story["title"]:
        story["title"] = f"{name}是做什麼的？"
    log(f"  AI 撰寫完成，刪掉 {dropped} 句無法查證的內容")

    # 名詞小辭典：每個名詞附資料來源（維基百科條目；沒有條目就附維基百科搜尋）
    for t in story["terms"]:
        url = wiki_link(t["term"])
        t["url"], t["url_label"] = (url, "維基百科") if url else (f"{WIKI}/w/index.php?search={quote(t['term'])}&variant=zh-tw", "維基百科搜尋")
        time.sleep(0.3)

    sources = []
    if prof:
        sources.append({"label": "證交所／櫃買中心公司基本資料（OpenAPI）", "url": prof["source"]})
    if wiki:
        sources.append({"label": f"維基百科：{wiki['title']}", "url": wiki["url"]})
    sources += [{"label": f"鉅亨網 {n['date']}：{n['title']}", "url": n["url"]} for n in news[:6]]
    sources += [{"label": f"{x['source']['publisher']} {x['source']['date']}：{x['source']['title']}", "url": x["source"]["url"]}
                for x in supply if x["source"].get("url")][:4]
    seen = set()
    sources = [x for x in sources if not (x["url"] in seen or seen.add(x["url"]))]
    if prof and prof.get("網址"):
        site = prof["網址"] if prof["網址"].startswith("http") else f"https://{prof['網址']}"
        sources.append({"label": f"{name} 官方網站", "url": site})

    v, m, rv = s.get("valuation") or {}, s.get("margins") or {}, s.get("revenue") or {}
    return {
        "date": today, "code": code, "name": s["name"], "market": s["market"], "industry": s.get("industry"),
        "story": story, "sources": sources, "dropped_sentences": dropped,
        "why": {"digest_mentions": why["mentions"], "news_7d": why["fresh"], "weekly": code in weekly, "supply": bool(links)},
        "snapshot": {"close": s.get("close"), "rev_yoy": rv.get("yoy"), "rev_month": rv.get("month"), "gross": m.get("gross"),
                     "pe": v.get("pe"), "yield": v.get("yield")},
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
    }


def main() -> int:
    today = datetime.now(TAIPEI).strftime("%Y-%m-%d")
    path = OUT_DIR / f"{today}.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if path.exists():
        pick = json.loads(path.read_text(encoding="utf-8"))
        log(f"⏭️ 今天已經選好：{pick['code']} {pick['name']}")
    else:
        if not GROQ_API_KEY:
            log("⛔ 沒有 GROQ_API_KEY")
            return 1
        pick = generate(today)
        path.write_text(json.dumps(pick, ensure_ascii=False, indent=1), encoding="utf-8")
    if os.environ.get("SEND") == "1" and not pick.get("emailed_at"):
        if send_email(pick):
            pick["emailed_at"] = datetime.now(TAIPEI).isoformat(timespec="minutes")
            path.write_text(json.dumps(pick, ensure_ascii=False, indent=1), encoding="utf-8")
    if os.environ.get("SEND") == "1" and not pick.get("line_sent_at"):
        if send_line(pick):
            pick["line_sent_at"] = datetime.now(TAIPEI).isoformat(timespec="minutes")
            path.write_text(json.dumps(pick, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
