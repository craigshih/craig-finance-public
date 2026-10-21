"""匯率頁：台幣兌美元、日圓、歐元的走勢，跟各地股市的連動，外資進出 vs 台幣，以及一段 AI 解讀。

資料全部來自 market.py 已經抓的指數日線（data/market/latest.json），這裡不另外抓資料。
AI 解讀跟 Discord 標題同一套規則：只能用這頁算出來的數字、不預測漲跌、不給買賣建議。
"""
import json
import statistics
import sys

from market_page import TAB_SCRIPT, cls, e, flow_bars, index_board

# (匯率, 「數字上升」代表什麼, 對照的股市)
PAIRS = [("TWD=X", "台幣轉弱", "^TWII"), ("JPYTWD=X", "日圓走強", "^N225"),
         ("EURTWD=X", "歐元走強", "^STOXX50E"), ("DX-Y.NYB", "美元走強", "^GSPC")]
DAYS = 60


def returns(ix: dict) -> dict:
    o = ix["ohlc"]
    return {o[i][0]: o[i][4] / o[i - 1][4] - 1 for i in range(1, len(o)) if o[i - 1][4]}


def correlations(m: dict) -> list[dict]:
    """近 60 個共同交易日的日報酬相關係數。"""
    ix = {i["ticker"]: i for i in m.get("indices") or []}
    out = []
    for fx, up, stock in PAIRS:
        if fx not in ix or stock not in ix:
            continue
        a, b = returns(ix[fx]), returns(ix[stock])
        days = sorted(set(a) & set(b))[-DAYS:]
        if len(days) < 20:
            continue
        r = statistics.correlation([a[d] for d in days], [b[d] for d in days])
        out.append({"fx": ix[fx]["name"], "up": up, "stock": ix[stock]["name"], "r": round(r, 2), "n": len(days)})
    return out


def describe(c: dict) -> str:
    r = c["r"]
    if abs(r) < 0.2:
        return f'{c["fx"]}和{c["stock"]}幾乎沒有連動'
    how = "明顯" if abs(r) >= 0.5 else "輕度"
    return f'{c["up"]}的日子，{c["stock"]}{how}傾向{"同步上漲" if r > 0 else "下跌"}'


def corr_table(cs: list[dict]) -> str:
    if not cs:
        return '<p class="empty">資料不足，暫時算不出連動</p>'
    rows = "".join(f'<tr><td>{e(c["fx"])}</td><td>{e(c["stock"])}</td><td class="num {cls(c["r"])}">{c["r"]:+.2f}</td>'
                   f'<td>{e(describe(c))}</td></tr>' for c in cs)
    return (f'<div class="table-wrap"><table class="holdings"><thead><tr><th>匯率</th><th>股市</th><th class="num">相關係數</th><th>過去的關係</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p class="mk-note">每日漲跌幅的相關係數，介於 -1 到 +1；近 {cs[0]["n"]} 個共同交易日的統計，不代表未來。</p>')


def flows_vs_twd(m: dict, w=1000, h=160) -> str:
    """外資買賣超（柱）跟同一段期間的美元兌台幣（線），x 軸對齊同一天。"""
    hist = m.get("history") or []
    twd = next((i for i in m.get("indices") or [] if i["ticker"] == "TWD=X"), None)
    if not hist or not twd:
        return '<p class="empty">資料暫時讀不到</p>'
    close = {d: c for d, *_, c in twd["ohlc"]}
    pts = [(i, close[x["date"]]) for i, x in enumerate(hist) if x["date"] in close]
    line = ""
    if len(pts) >= 2:
        lo, hi = min(v for _, v in pts), max(v for _, v in pts)
        span, n = hi - lo or 1, len(hist) - 1 or 1
        # 柱子畫在每格中間，線也對到每格中間
        poly = " ".join(f"{(i + 0.5) / (n + 1) * w:.1f},{h - 8 - (v - lo) / span * (h - 16):.1f}" for i, v in pts)
        line = (f'<svg class="mk-line" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><polyline points="{poly}"/></svg>'
                f'<div class="mk-axis"><span>{e(hist[0]["date"])}</span><span>美元兌台幣 {lo:.2f}～{hi:.2f}（越高＝台幣越弱）</span><span>{e(hist[-1]["date"])}</span></div>')
    return flow_bars(hist, "foreign") + line


def facts(m: dict, cs: list[dict]) -> dict:
    ix = {i["ticker"]: i for i in m.get("indices") or []}
    hist = (m.get("history") or [])[-5:]
    return {
        "匯率": {ix[t]["name"]: {"收盤": ix[t]["close"], "漲跌%": ix[t]["chg_pct"]} for t, *_ in PAIRS if t in ix},
        "股市": {ix[t]["name"]: {"漲跌%": ix[t]["chg_pct"]} for *_, t in PAIRS if t in ix},
        "近60日相關係數": {f'{c["fx"]} vs {c["stock"]}': c["r"] for c in cs},
        "外資近5日買賣超合計（億元）": round(sum(x.get("foreign") or 0 for x in hist), 1) if hist else None,
    }


PROMPT = """你是財經網站的編輯。依下面 JSON 資料，寫 2 到 3 句「匯率對台股、日股、歐股、美股可能帶來的影響」。
語氣直接，繁體中文，150 字以內。
規則：
- 只能用資料裡出現的數字，不要自己計算新數字，也不要補充資料以外的事實
- 相關係數是過去的統計，不要寫成會發生的事；不預測漲跌，不給買賣建議，不提目標價
回傳 JSON：{{"text": "那幾句話"}}

資料：
{data}"""


def ai_view(f: dict) -> str:
    """沒有金鑰、失敗或沒通過檢查就回空字串（整段不顯示）。"""
    import picks
    from discord_push import numbers_ok

    if not picks.GROQ_API_KEY:
        return ""
    data = json.dumps(f, ensure_ascii=False)
    try:
        text = str(json.loads(picks.call_groq(PROMPT.format(data=data))).get("text") or "").strip()
    except Exception as exc:  # noqa: BLE001 — AI 失敗不能讓整個建站失敗
        print(f"⚠️ 匯率 AI 解讀失敗：{exc}", file=sys.stderr)
        return ""
    if not text or len(text) > 300 or picks.has_banned(text) or not numbers_ok(text, data):
        print(f"⚠️ 匯率 AI 解讀沒通過檢查，不顯示：{text}", file=sys.stderr)
        return ""
    return text


def render(m: dict | None, hero, section) -> str:
    fx = [i for i in (m or {}).get("indices") or [] if i["region"] == "匯率"]
    if not fx:
        return hero("匯率", "匯率資料準備中", "下一次網站更新後就會出現。")
    cs = correlations(m)
    body = hero("匯率", "台幣跟著誰走", f"台幣兌美元、日圓、歐元的走勢，以及匯率和各地股市的連動・資料日 {e(fx[0]['date'])}")
    body += '<main class="wrap">'
    body += section("匯率走勢", index_board(fx, "fx"), '<span class="live-dot"></span><span class="live-stamp">盤中即時更新</span>・點卡片看近半年日 K・台幣匯率數字越大＝台幣越弱')
    view = ai_view(facts(m, cs))
    if view:
        body += section("AI 解讀", f'<p>{e(view)}</p>', "AI 依本頁數字整理，僅供學習研究，不構成投資建議")
    body += section("匯率與股市連動", corr_table(cs), "美元／台幣 vs 台股・100 日圓／台幣 vs 日經・歐元／台幣 vs 歐洲 STOXX 50・美元指數 vs S&P 500")
    body += section("外資進出 vs 台幣", flows_vs_twd(m), "上：外資買賣超（上市，億元）・下：美元兌台幣收盤")
    return body + "</main>" + TAB_SCRIPT
