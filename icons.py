"""
Q 版主題圖示：取代每日總經裡畫質不好的新聞縮圖。

每個主題是一隻有表情的小角色（晶片、油桶、聯準會、機器人…），依新聞標題的漲跌語氣換表情（開心／擔心）。
全部是向量 SVG，任何尺寸都清楚；動畫（上下飄、閃光）寫在 style.css 的 .qicon。
同一份主題關鍵字也輸出成 site/topics.js，讓即時快報頁的前端用同一套圖示。
"""

import json
import re
from html import escape

# いらすとや風：細的暖棕色外框、柔和粉彩色、簡單的臉（2026-10-09 改版）
INK = "#5b4740"
RED, YELLOW, CREAM, ORANGE, DARK, GREY = "#ef7468", "#f9d36b", "#fff6e6", "#f5a865", "#5f6577", "#d3cbc0"

# (主題代號, 標籤, 關鍵字)；依序比對，越前面優先
TOPICS = [
    ("fed", "利率央行", ["聯準會", "Fed", "FOMC", "降息", "升息", "利率", "鮑爾", "央行", "公債", "殖利率", "債券", "債市"]),
    ("chip", "半導體", ["半導體", "晶片", "晶圓", "台積電", "輝達", "NVIDIA", "Nvidia", "CoWoS", "記憶體", "HBM", "先進製程", "IC 設計", "封測"]),
    ("ai", "AI", ["AI", "人工智慧", "伺服器", "資料中心", "OpenAI", "算力", "雲端", "機器人", "大模型"]),
    ("oil", "能源", ["原油", "油價", "OPEC", "天然氣", "石油", "能源"]),
    ("inflation", "通膨", ["通膨", "CPI", "PCE", "PPI", "物價"]),
    ("jobs", "就業", ["非農", "就業", "失業", "薪資", "職缺", "勞動", "裁員"]),
    ("trade", "貿易", ["關稅", "貿易", "出口", "進口", "海運", "航運", "供應鏈", "川普"]),
    ("gold", "黃金", ["黃金", "金價", "白銀", "貴金屬"]),
    ("crypto", "加密貨幣", ["比特幣", "加密", "虛擬貨幣", "以太幣", "穩定幣"]),
    ("house", "房市", ["房市", "房價", "營建", "不動產", "房地產", "建商"]),
    ("car", "汽車", ["電動車", "特斯拉", "汽車", "車用"]),
    ("earn", "財報營收", ["營收", "財報", "EPS", "獲利", "法說", "毛利", "季報", "年報"]),
    ("shop", "消費", ["零售", "消費", "電商", "百貨", "餐飲"]),
    ("fx", "匯率", ["美元", "匯率", "台幣", "新台幣", "日圓", "外匯", "人民幣"]),
    ("globe", "國際", ["中國", "歐洲", "日本", "韓國", "全球", "地緣", "戰爭", "陸股", "港股"]),
    ("stocks", "股市", []),
]
LABELS = {k: label for k, label, _ in TOPICS}
NEGATIVE = ["跌", "挫", "衰退", "下修", "警告", "崩", "疲軟", "降評", "虧損", "減少", "萎縮", "危機", "賣壓", "重創", "暴跌", "放緩", "低迷"]
POSITIVE = ["漲", "創高", "新高", "大增", "成長", "上修", "強勁", "勁揚", "大漲", "暢旺", "看好", "回升", "噴"]


def topic_of(text: str) -> str:
    for key, _, kws in TOPICS:
        if any(k in text for k in kws):
            return key
    return "stocks"


def mood_of(text: str) -> str:
    neg = sum(text.count(w) for w in NEGATIVE)
    pos = sum(text.count(w) for w in POSITIVE)
    return "sad" if neg > pos else "happy" if pos > neg else "calm"


def face(cx: float, cy: float, s: float = 1.0, mood: str = "happy") -> str:
    """いらすとや風的臉：小黑豆眼（不加高光）、短短的嘴、圓圓的粉紅臉頰。"""
    ex = 8.5 * s
    eyes = "".join(f'<ellipse cx="{cx + dx:.1f}" cy="{cy:.1f}" rx="{2.4 * s:.1f}" ry="{3.1 * s:.1f}" fill="{INK}"/>' for dx in (-ex, ex))
    blush = "".join(f'<circle cx="{cx + dx:.1f}" cy="{cy + 6 * s:.1f}" r="{3.6 * s:.1f}" fill="#f6a5a0" opacity=".75"/>'
                    for dx in (-ex - 4.5 * s, ex + 4.5 * s))
    my = cy + 6.5 * s
    if mood == "calm":
        mood = "happy"
    if mood == "sad":
        mouth = f'<path d="M{cx - 4 * s:.1f} {my + 2.5 * s:.1f} Q{cx:.1f} {my - 1.5 * s:.1f} {cx + 4 * s:.1f} {my + 2.5 * s:.1f}" fill="none" stroke="{INK}" stroke-width="{1.8 * s:.1f}" stroke-linecap="round"/>'
        sweat = f'<path class="drop" d="M{cx + ex + 8 * s:.1f} {cy - 8 * s:.1f} q{2.6 * s:.1f} {4.5 * s:.1f} 0 {6.2 * s:.1f} q-{2.6 * s:.1f} -{1.7 * s:.1f} 0 -{6.2 * s:.1f}z" fill="#bfe3ff" stroke="{INK}" stroke-width="{1 * s:.1f}"/>'
        return eyes + blush + mouth + sweat
    mouth = f'<path d="M{cx - 4.5 * s:.1f} {my:.1f} Q{cx:.1f} {my + 4.5 * s:.1f} {cx + 4.5 * s:.1f} {my:.1f}" fill="none" stroke="{INK}" stroke-width="{1.8 * s:.1f}" stroke-linecap="round"/>'
    return eyes + blush + mouth


def sparkles() -> str:
    star = lambda x, y, r, c: (f'<path class="tw" style="--t:{(x + y) % 7 * .3:.1f}s" d="M{x} {y - r} L{x + r * .3} {y - r * .3} L{x + r} {y} '  # noqa: E731
                               f'L{x + r * .3} {y + r * .3} L{x} {y + r} L{x - r * .3} {y + r * .3} L{x - r} {y} L{x - r * .3} {y - r * .3}Z" fill="{c}"/>')
    return star(18, 22, 7, YELLOW) + star(102, 30, 5, CREAM) + star(100, 96, 6, YELLOW)


S = f'stroke="{INK}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"'


def body(topic: str, mood: str) -> str:
    """每個角色的身體（viewBox 0 0 120 120），臉畫在身體中央。"""
    if topic == "chip":
        pins = "".join(f'<rect x="{x}" y="22" width="6" height="12" rx="2" fill="{GREY}" {S}/><rect x="{x}" y="86" width="6" height="12" rx="2" fill="{GREY}" {S}/>'
                       f'<rect x="22" y="{x}" width="12" height="6" rx="2" fill="{GREY}" {S}/><rect x="86" y="{x}" width="12" height="6" rx="2" fill="{GREY}" {S}/>'
                       for x in (42, 57, 72))
        return pins + f'<rect x="30" y="30" width="60" height="60" rx="12" fill="{DARK}" {S}/><rect x="38" y="38" width="44" height="44" rx="8" fill="{YELLOW}" {S}/>' + face(60, 58, .95, mood)
    if topic == "ai":
        return (f'<line x1="60" y1="24" x2="60" y2="12" {S}/><circle class="blink" cx="60" cy="11" r="5" fill="{RED}" {S}/>'
                f'<rect x="20" y="52" width="10" height="20" rx="4" fill="{RED}" {S}/><rect x="90" y="52" width="10" height="20" rx="4" fill="{RED}" {S}/>'
                f'<rect x="28" y="26" width="64" height="66" rx="20" fill="{CREAM}" {S}/><rect x="36" y="40" width="48" height="34" rx="12" fill="{DARK}" {S}/>'
                + face(60, 54, .85, mood).replace(INK, YELLOW).replace('fill="#fff"', f'fill="{DARK}"') +
                f'<rect x="44" y="80" width="32" height="6" rx="3" fill="{YELLOW}" {S}/>')
    if topic == "oil":
        return (f'<path class="drip" d="M92 14 q8 12 0 18 q-8 -6 0 -18z" fill="{INK}"/>'
                f'<rect x="30" y="24" width="60" height="78" rx="10" fill="{RED}" {S}/><ellipse cx="60" cy="24" rx="30" ry="7" fill="#d9594e" {S}/>'
                f'<line x1="31" y1="46" x2="89" y2="46" {S}/><line x1="31" y1="84" x2="89" y2="84" {S}/>' + face(60, 62, 1, mood))
    if topic == "fed":
        cols = "".join(f'<rect x="{x}" y="52" width="10" height="36" rx="2" fill="{CREAM}" {S}/>' for x in (26, 44, 66, 84))
        return (f'<path d="M16 46 L60 18 L104 46 Z" fill="{YELLOW}" {S}/><rect x="20" y="44" width="80" height="8" rx="2" fill="{CREAM}" {S}/>'
                + cols + f'<rect x="16" y="88" width="88" height="12" rx="3" fill="{RED}" {S}/>' + face(60, 32, .7, mood))
    if topic == "inflation":
        return (f'<path d="M22 50 L54 18 L100 18 L100 64 L68 96 Z" fill="{YELLOW}" {S}/><circle cx="86" cy="32" r="6" fill="{CREAM}" {S}/>'
                f'<path class="arrow" d="M30 108 L46 92 M38 92 L46 92 L46 100" fill="none" stroke="{RED}" stroke-width="3.1" stroke-linecap="round" stroke-linejoin="round"/>'
                + face(62, 54, .95, mood))
    if topic == "jobs":
        return (f'<path d="M46 36 V28 a6 6 0 0 1 6 -6 h16 a6 6 0 0 1 6 6 V36" fill="none" {S}/>'
                f'<rect x="18" y="36" width="84" height="62" rx="12" fill="{ORANGE}" {S}/><rect x="52" y="56" width="16" height="10" rx="3" fill="{YELLOW}" {S}/>'
                + face(60, 76, .85, mood))
    if topic == "trade":
        return (f'<path class="wave" d="M8 100 q10 -8 20 0 t20 0 t20 0 t20 0 t20 0 t20 0" fill="none" stroke="#86bfe8" stroke-width="2.5" stroke-linecap="round"/>'
                f'<rect x="30" y="36" width="26" height="22" rx="3" fill="{YELLOW}" {S}/><rect x="58" y="30" width="30" height="28" rx="3" fill="{RED}" {S}/>'
                f'<path d="M14 58 H106 L94 92 H26 Z" fill="{DARK}" {S}/>' + face(60, 70, .8, mood).replace(INK, CREAM).replace('fill="#fff"', f'fill="{INK}"'))
    if topic == "gold":
        return (f'<path d="M20 86 L34 50 H86 L100 86 Z" fill="{YELLOW}" {S}/><path d="M34 50 L42 38 H78 L86 50" fill="#fbe4a0" {S}/>' + face(60, 68, .95, mood))
    if topic == "crypto":
        return (f'<circle cx="60" cy="60" r="40" fill="{ORANGE}" {S}/><circle cx="60" cy="60" r="31" fill="none" stroke="#ffe0b8" stroke-width="2.5"/>'
                f'<text x="60" y="44" text-anchor="middle" font-size="20" font-weight="900" fill="{CREAM}" font-family="Arial">₿</text>' + face(60, 64, .9, mood))
    if topic == "house":
        return (f'<path d="M14 58 L60 20 L106 58" fill="none" {S}/><path d="M24 52 L60 24 L96 52 V100 H24 Z" fill="{CREAM}" {S}/>'
                f'<rect x="72" y="26" width="10" height="18" fill="{RED}" {S}/><rect x="52" y="78" width="16" height="22" rx="3" fill="{RED}" {S}/>' + face(60, 58, .85, mood))
    if topic == "car":
        return (f'<path d="M18 74 Q20 56 36 54 L46 38 H76 L88 54 Q104 56 104 74 V84 H18 Z" fill="{RED}" {S}/>'
                f'<path d="M50 42 H72 L80 54 H44 Z" fill="#c5e5ff" {S}/><circle cx="38" cy="86" r="10" fill="{DARK}" {S}/><circle cx="84" cy="86" r="10" fill="{DARK}" {S}/>'
                + face(61, 68, .7, mood))
    if topic == "shop":
        return (f'<path d="M44 40 V34 a16 16 0 0 1 32 0 V40" fill="none" {S}/><path d="M26 40 H94 L100 102 H20 Z" fill="{RED}" {S}/>' + face(60, 68, 1, mood))
    if topic == "fx":
        return (f'<circle cx="46" cy="70" r="30" fill="{GREY}" {S}/><circle cx="72" cy="54" r="32" fill="{YELLOW}" {S}/>'
                f'<text x="72" y="44" text-anchor="middle" font-size="18" font-weight="900" fill="{INK}" font-family="Arial">$</text>' + face(72, 60, .8, mood))
    if topic == "globe":
        return (f'<circle cx="60" cy="60" r="42" fill="#86bfe8" {S}/>'
                f'<path d="M34 34 q14 6 10 18 q-6 8 4 16 q6 8 -2 18 M74 22 q-6 12 6 16 q14 2 12 16 q-2 10 10 12" fill="#a3dba6" stroke="{INK}" stroke-width="2.2" stroke-linejoin="round"/>'
                + face(60, 62, 1, mood))
    if topic == "earn":
        return (f'<rect x="26" y="18" width="68" height="86" rx="10" fill="{CREAM}" {S}/><rect x="44" y="12" width="32" height="14" rx="5" fill="{RED}" {S}/>'
                f'<rect class="bar1" x="38" y="78" width="10" height="14" rx="2" fill="{YELLOW}" {S}/><rect class="bar2" x="55" y="70" width="10" height="22" rx="2" fill="{ORANGE}" {S}/>'
                f'<rect class="bar3" x="72" y="60" width="10" height="32" rx="2" fill="{RED}" {S}/>' + face(60, 44, .85, mood))
    if topic == "stocks" and mood == "happy":  # 牛
        return (f'<path d="M30 40 Q16 30 20 14 Q30 28 42 32 Z" fill="{CREAM}" {S}/><path d="M90 40 Q104 30 100 14 Q90 28 78 32 Z" fill="{CREAM}" {S}/>'
                f'<ellipse cx="22" cy="54" rx="12" ry="8" fill="{RED}" {S}/><ellipse cx="98" cy="54" rx="12" ry="8" fill="{RED}" {S}/>'
                f'<rect x="28" y="30" width="64" height="66" rx="30" fill="{RED}" {S}/><ellipse cx="60" cy="82" rx="22" ry="13" fill="#ffc9c0" {S}/>'
                f'<circle cx="53" cy="82" r="2.6" fill="{INK}"/><circle cx="67" cy="82" r="2.6" fill="{INK}"/>'
                f'<path class="arrow" d="M96 100 L110 86 M101 86 L110 86 L110 95" fill="none" stroke="{YELLOW}" stroke-width="3.1" stroke-linecap="round" stroke-linejoin="round"/>'
                + face(60, 58, .85, "happy").replace('<path d="M', '<path opacity="0" d="M', 1))
    if topic == "stocks" and mood == "sad":  # 熊
        return (f'<circle cx="32" cy="32" r="12" fill="#b08968" {S}/><circle cx="88" cy="32" r="12" fill="#b08968" {S}/>'
                f'<circle cx="32" cy="32" r="5" fill="#e2c4a4"/><circle cx="88" cy="32" r="5" fill="#e2c4a4"/>'
                f'<circle cx="60" cy="62" r="38" fill="#b08968" {S}/><ellipse cx="60" cy="76" rx="16" ry="12" fill="#e2c4a4" {S}/>'
                f'<ellipse cx="60" cy="70" rx="5" ry="3.5" fill="{INK}"/>'
                f'<path class="arrow" d="M96 86 L110 100 M101 100 L110 100 L110 91" fill="none" stroke="#6cc58a" stroke-width="3.1" stroke-linecap="round" stroke-linejoin="round"/>'
                + face(60, 56, .85, "sad"))
    # 股市：K 線看板
    return (f'<rect x="16" y="22" width="88" height="76" rx="14" fill="{DARK}" {S}/>'
            f'<line x1="36" y1="34" x2="36" y2="58" stroke="{RED}" stroke-width="1.9"/><rect x="31" y="38" width="10" height="14" rx="2" fill="{RED}"/>'
            f'<line x1="56" y1="30" x2="56" y2="52" stroke="#6cc58a" stroke-width="1.9"/><rect x="51" y="34" width="10" height="12" rx="2" fill="#6cc58a"/>'
            f'<line x1="78" y1="26" x2="78" y2="50" stroke="{RED}" stroke-width="1.9"/><rect x="73" y="28" width="10" height="16" rx="2" fill="{RED}"/>'
            + face(60, 74, .9, mood).replace(INK, YELLOW).replace('fill="#fff"', f'fill="{DARK}"'))


def qicon(topic: str, mood: str = "happy", cls: str = "", title: str = "") -> str:
    t = f"<title>{escape(title)}</title>" if title else ""
    return (f'<svg class="qicon {cls}" viewBox="0 0 120 120" role="img" aria-label="{escape(LABELS.get(topic, ""))}">{t}'
            f'{sparkles()}<g class="bob">{body(topic, mood)}</g></svg>')


def article_icon(a: dict) -> str:
    text = f'{a.get("title", "")} {" ".join(a.get("keywords") or [])}'
    topic = topic_of(text)
    return (f'<div class="cover qcover t-{topic}">{qicon(topic, mood_of(a.get("title", "")))}'
            f'<span class="qtag">{escape(LABELS[topic])}</span></div>')


def digest_topics(d: dict) -> list[tuple[str, str, int]]:
    """當天新聞的主題排行：(主題, 表情, 篇數)。表情看該主題標題整體的語氣。"""
    count: dict[str, list[str]] = {}
    for sec in d.get("news_sections", []):
        for a in sec.get("articles", []):
            title = a.get("title", "")
            count.setdefault(topic_of(f'{title} {" ".join(a.get("keywords") or [])}'), []).append(title)
    ranked = sorted(count.items(), key=lambda kv: (kv[0] == "stocks", -len(kv[1])))
    return [(k, mood_of(" ".join(ts)), len(ts)) for k, ts in ranked]


def digest_cover(d: dict) -> str:
    """每日總經目錄卡封面：當天最多新聞的主題當主角，旁邊 3 個小配角。"""
    ranked = digest_topics(d) or [("stocks", "happy", 0)]
    main, mood, _ = ranked[0]
    minis = "".join(f'<span class="qmini" style="--i:{i}">{qicon(k, m)}<b>{escape(LABELS[k])}</b></span>'
                    for i, (k, m, _) in enumerate(ranked[1:4]))
    return (f'<div class="qart t-{main}"><div class="rays"></div>{qicon(main, mood, "main")}'
            f'<div class="qminis">{minis}</div></div>')


def topics_js() -> str:
    """給即時快報頁用：同一套關鍵字與 SVG。"""
    icons = {k: {m: qicon(k, m) for m in ("happy", "sad", "calm")} for k, _, _ in TOPICS}
    return ("window.QTOPICS=" + json.dumps({"topics": [[k, label, kws] for k, label, kws in TOPICS], "neg": NEGATIVE, "pos": POSITIVE,
                                             "icons": icons}, ensure_ascii=False) + ";")


def strip(text: str) -> str:
    return re.sub(r"\s+", " ", text)
