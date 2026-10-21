"""匯率頁：台幣兌美元、日圓、歐元的走勢，跟各地股市的連動，外資進出 vs 台幣，以及一段 AI 解讀。

資料全部來自 market.py 已經抓的指數日線（data/market/latest.json），這裡不另外抓資料。
AI 解讀跟 Discord 標題同一套規則：只能用這頁算出來的數字、不預測漲跌、不給買賣建議。
"""
import json
import statistics
import sys

from market_page import TAB_SCRIPT, cls, e, flow_bars, index_board, tabs

# (匯率, 「數字上升」代表什麼, 對照的股市)
PAIRS = [("TWD=X", "台幣轉弱", "^TWII"), ("JPYTWD=X", "日圓走強", "^N225"),
         ("EURTWD=X", "歐元走強", "^STOXX50E"), ("DX-Y.NYB", "美元走強", "^GSPC")]
# 避險情緒：市場緊張（VIX 上升）時，資金常流向日圓、美元
HEDGE = [("^VIX", "市場恐慌升高", "JPYTWD=X"), ("^VIX", "市場恐慌升高", "DX-Y.NYB")]
DAYS = 60


def returns(ix: dict) -> dict:
    o = ix["ohlc"]
    return {o[i][0]: o[i][4] / o[i - 1][4] - 1 for i in range(1, len(o)) if o[i - 1][4]}


def correlations(m: dict, pairs=PAIRS) -> list[dict]:
    """近 60 個共同交易日的日報酬相關係數。"""
    ix = {i["ticker"]: i for i in m.get("indices") or []}
    out = []
    for fx, up, stock in pairs:
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


def corr_table(cs: list[dict], head=("匯率", "股市")) -> str:
    if not cs:
        return '<p class="empty">資料不足，暫時算不出連動</p>'
    rows = "".join(f'<tr><td>{e(c["fx"])}</td><td>{e(c["stock"])}</td><td class="num {cls(c["r"])}">{c["r"]:+.2f}</td>'
                   f'<td>{e(describe(c))}</td></tr>' for c in cs)
    return (f'<div class="table-wrap"><table class="holdings"><thead><tr><th>{head[0]}</th><th>{head[1]}</th><th class="num">相關係數</th><th>過去的關係</th></tr></thead><tbody>{rows}</tbody></table></div>'
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


RANGES = [("90", "3 個月"), ("365", "1 年"), ("1095", "3 年"), ("1825", "5 年"), ("3650", "10 年")]

LONG_SCRIPT = """<script>
(() => {
  const box = document.getElementById("fx-long");
  if (!box) return;
  const data = JSON.parse(document.getElementById("fx-long-data").textContent);
  const svg = box.querySelector("svg"), tip = box.querySelector(".fx-tip");
  let cur = box.querySelector('[data-tabs="fxcur"] .on').dataset.tab, days = +box.querySelector('[data-tabs="fxrange"] .on').dataset.tab;
  let pts = [], ref = null;
  const W = 1000, H = 300, R = 64, B = 24, T = 8;  // 右邊留給價格刻度、下面留給日期
  const fmt = (v) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: v < 10 ? 3 : 2 });
  let lo, hi, x, y;
  const el = (tag, attrs, text) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    return n;
  };
  function draw() {
    const all = data[cur].closes, end = new Date(all[all.length - 1][0]);
    const from = new Date(end - days * 864e5).toISOString().slice(0, 10);
    pts = all.filter((r) => r[0] >= from);
    const vs = pts.map((r) => r[1]);
    lo = Math.min(...vs); hi = Math.max(...vs);
    const span = hi - lo || 1;
    x = (i) => i / (pts.length - 1) * (W - R);
    y = (v) => T + (hi - v) / span * (H - B - T * 2);
    svg.replaceChildren();
    // 價格虛線：5 條等距，右邊標價格
    for (let k = 0; k < 5; k++) {
      const v = lo + span * k / 4;
      svg.append(el("line", { class: "grid fx-dash", x1: 0, x2: W - R, y1: y(v), y2: y(v) }), el("text", { class: "ax", x: W - R + 6, y: y(v) + 4 }, fmt(v)));
    }
    // 時間刻度：約 6 個，短期標月/日、長期標年-月
    const n = 6;
    for (let k = 0; k <= n; k++) {
      const i = Math.round(k / n * (pts.length - 1)), d = pts[i][0];
      svg.append(el("line", { class: "grid fx-dash", x1: x(i), x2: x(i), y1: T, y2: H - B }),
        el("text", { class: "ax", x: x(i), y: H - 6, "text-anchor": k === 0 ? "start" : k === n ? "end" : "middle" },
          days <= 365 ? `${+d.slice(5, 7)}/${+d.slice(8)}` : d.slice(0, 7)));
    }
    const last = vs[vs.length - 1];
    svg.append(el("line", { class: "last", x1: 0, x2: W - R, y1: y(last), y2: y(last) }),
      el("polyline", { points: pts.map((r, i) => `${x(i).toFixed(1)},${y(r[1]).toFixed(1)}`).join(" ") }));
    ref = null;
    svg.append(el("g", { class: "fx-ref" }), el("g", { class: "fx-hover" }));
    tip.textContent = "滑過圖表看當天價格・點一下留下一條基準線，再滑到其他日期比較";
    // 年化波動率：日對數報酬的標準差 × √252
    const rs = vs.slice(1).map((v, i) => Math.log(v / vs[i])), mean = rs.reduce((a, b) => a + b, 0) / rs.length;
    const vol = Math.sqrt(rs.reduce((a, b) => a + (b - mean) ** 2, 0) / (rs.length - 1) * 252) * 100;
    const chg = (last / vs[0] - 1) * 100;
    const at = (v) => pts[vs.indexOf(v)][0];
    const tile = (k, v, foot, c = "") => `<div class="stat"><div class="stat-label">${k}</div><div class="stat-value ${c}">${v}</div><div class="stat-foot"><span>${foot}</span></div></div>`;
    box.querySelector(".stats").innerHTML =
      tile("期間漲跌", `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`, `${pts[0][0]} ${fmt(vs[0])} → ${fmt(last)}`, chg > 0 ? "pos" : chg < 0 ? "neg" : "") +
      tile("期間最高", fmt(hi), at(hi)) + tile("期間最低", fmt(lo), at(lo)) +
      tile("高低差", `${((hi / lo - 1) * 100).toFixed(1)}%`, "最高比最低多幾 %") +
      tile("年化波動率", `${vol.toFixed(1)}%`, "日漲跌的標準差 × √252");
  }
  // 滑鼠／手指位置 → 最接近的那一天
  const pick = (ev) => {
    const p = ev.touches ? ev.touches[0] : ev, r = svg.getBoundingClientRect();
    const px = (p.clientX - r.left) / r.width * W;
    return Math.max(0, Math.min(pts.length - 1, Math.round(px / (W - R) * (pts.length - 1))));
  };
  const mark = (g, i, label) => {
    const [d, v] = pts[i];
    g.replaceChildren(el("line", { class: "fx-cross", x1: 0, x2: W - R, y1: y(v), y2: y(v) }),
      el("line", { class: "fx-cross", x1: x(i), x2: x(i), y1: T, y2: H - B }),
      el("circle", { class: "fx-dot", cx: x(i), cy: y(v), r: 4 }),
      el("text", { class: "fx-label", x: Math.min(x(i) + 8, W - R - 150), y: Math.max(y(v) - 8, 16) }, label || `${d}  ${fmt(v)}`));
  };
  const move = (ev) => {
    if (!pts.length) return;
    const i = pick(ev), [d, v] = pts[i];
    mark(svg.querySelector(".fx-hover"), i);
    tip.textContent = ref ? `${d}　${fmt(v)}　比基準（${ref[0]} ${fmt(ref[1])}）${v >= ref[1] ? "+" : ""}${((v / ref[1] - 1) * 100).toFixed(2)}%` : `${d}　${fmt(v)}`;
  };
  svg.addEventListener("mousemove", move);
  svg.addEventListener("touchmove", move, { passive: true });
  svg.addEventListener("click", (ev) => {
    const i = pick(ev);
    ref = pts[i];
    mark(svg.querySelector(".fx-ref"), i, `基準 ${ref[0]}  ${fmt(ref[1])}`);
    move(ev);
  });
  box.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-tab]");
    if (!b) return;
    if (b.closest('[data-tabs="fxcur"]')) cur = b.dataset.tab; else days = +b.dataset.tab;
    draw();
  });
  draw();
})();
</script>"""


def long_chart(hist: dict | None) -> str:
    """匯率長期走勢：選幣別、選時長；有日期刻度、價格虛線，滑過看當天價格、點一下留基準線比較。"""
    if not hist:
        return '<p class="empty">長期資料暫時讀不到</p>'
    keys = [t for t, *_ in PAIRS if t in hist]
    data = json.dumps(hist, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (f'<div id="fx-long">{tabs("fxcur", [(t, hist[t]["name"]) for t in keys], keys[0])} {tabs("fxrange", RANGES, "1095")}'
            '<div class="mk-chart"><svg class="mk-candles fx-long-svg" viewBox="0 0 1000 300" role="img" aria-label="匯率長期走勢"></svg>'
            '<p class="mk-note fx-tip"></p></div><div class="stats"></div></div>'
            f'<script type="application/json" id="fx-long-data">{data}</script>{LONG_SCRIPT}')


def facts(m: dict, cs: list[dict]) -> dict:
    ix = {i["ticker"]: i for i in m.get("indices") or []}
    hist = (m.get("history") or [])[-5:]
    vix = ix.get("^VIX")
    return {
        "VIX 恐慌指數": vix and {"收盤": vix["close"], "漲跌%": vix["chg_pct"]},
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


def render(m: dict | None, hero, section, hist: dict | None = None) -> str:
    fx = [i for i in (m or {}).get("indices") or [] if i["region"] == "匯率"]
    if not fx:
        return hero("匯率", "匯率資料準備中", "下一次網站更新後就會出現。")
    cs, hedge = correlations(m), correlations(m, HEDGE)
    body = hero("匯率", "台幣跟著誰走", f"台幣兌美元、日圓、歐元的走勢，以及匯率和各地股市的連動・資料日 {e(fx[0]['date'])}")
    body += '<main class="wrap">'
    body += section("匯率走勢", index_board(fx, "fx"), '<span class="live-dot"></span><span class="live-stamp">盤中即時更新</span>・點卡片看近半年日 K・台幣匯率數字越大＝台幣越弱')
    body += section("長期走勢", long_chart(hist), "選幣別與時長・最長近 10 年日收盤")
    view = ai_view(facts(m, cs + hedge))
    if view:
        body += section("AI 解讀", f'<p>{e(view)}</p>', "AI 依本頁數字整理，僅供學習研究，不構成投資建議")
    body += section("匯率與股市連動", corr_table(cs), "美元／台幣 vs 台股・100 日圓／台幣 vs 日經・歐元／台幣 vs 歐洲 STOXX 50・美元指數 vs S&P 500")
    body += section("避險情緒", corr_table(hedge, ("恐慌指標", "匯率")), "市場緊張時，資金常流向日圓、美元：看 VIX 上升的日子，日圓、美元是否同步走強")
    body += section("外資進出 vs 台幣", flows_vs_twd(m), "上：外資買賣超（上市，億元）・下：美元兌台幣收盤")
    return body + "</main>" + TAB_SCRIPT
