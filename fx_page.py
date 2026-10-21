"""匯率頁：台幣兌美元、日圓、歐元的走勢，跟各地股市的連動，外資進出 vs 台幣，以及一段 AI 解讀。

資料全部來自 market.py 已經抓的指數日線（data/market/latest.json），這裡不另外抓資料。
AI 解讀跟 Discord 標題同一套規則：只能用這頁算出來的數字、不預測漲跌、不給買賣建議。
AI 解讀由 market.py 呼叫 refresh_ai() 一天最多產生一次、存成 fx_ai.json；建站只讀檔（網站每 10 分鐘重建也不會一直呼叫 AI）。
"""
import json
import os
import statistics
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_page import TAB_SCRIPT, cls, e, index_board, tabs

def read_json(path: Path) -> dict:
    """讀快取；不存在或內容壞掉都回空的，讓呼叫的人重建。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_json(path: Path, obj) -> None:
    """先寫暫存檔再整個換過去，寫到一半被中斷也不會留下壞掉的檔案。"""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


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


RANGES = [("90", "3 個月"), ("365", "1 年"), ("1095", "3 年"), ("1825", "5 年"), ("3650", "10 年")]

# 兩張可調時長的圖共用：長期匯率（線）、外資買賣超（柱）vs 美元兌台幣（線）
CHART_SCRIPT = """<script>
(() => {
  const blob = document.getElementById("fx-long-data");
  if (!blob) return;
  const data = JSON.parse(blob.textContent);
  const W = 1000, R = 64;  // 右邊留給刻度
  const el = (tag, attrs, text) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    return n;
  };
  const fmt = (v) => v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: v < 10 ? 3 : 2 });
  const yi = (v) => `${v > 0 ? "+" : ""}${v.toLocaleString("en-US", { maximumFractionDigits: 1 })} 億`;
  const pct = (a, b) => `${b >= a ? "+" : ""}${((b / a - 1) * 100).toFixed(2)}%`;
  const since = (rows, days) => {
    const end = new Date(rows[rows.length - 1][0]);
    const from = new Date(end - days * 864e5).toISOString().slice(0, 10);
    return rows.filter((r) => r[0] >= from);
  };
  const tile = (k, v, foot, c = "") => `<div class="stat"><div class="stat-label">${k}</div><div class="stat-value ${c}">${v}</div><div class="stat-foot"><span>${foot}</span></div></div>`;
  const tone = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
  // 價格虛線：右邊標數字
  const hgrid = (svg, lo, hi, y, n, f) => {
    for (let k = 0; k < n; k++) {
      const v = lo + (hi - lo) * k / (n - 1);
      svg.append(el("line", { class: "grid fx-dash", x1: 0, x2: W - R, y1: y(v), y2: y(v) }), el("text", { class: "ax", x: W - R + 6, y: y(v) + 4 }, f(v)));
    }
  };
  // 時間刻度：約 6 段，短期標月/日、長期標年-月
  const vticks = (svg, keys, x, top, bottom, days) => {
    const n = 6;
    for (let k = 0; k <= n; k++) {
      const i = Math.round(k / n * (keys.length - 1)), d = keys[i];
      svg.append(el("line", { class: "grid fx-dash", x1: x(i), x2: x(i), y1: top, y2: bottom }),
        el("text", { class: "ax", x: x(i), y: bottom + 18, "text-anchor": k === 0 ? "start" : k === n ? "end" : "middle" },
          days <= 365 ? `${+d.slice(5, 7)}/${+d.slice(8, 10) || 1}` : d.slice(0, 7)));
    }
  };
  const label = (g, x, y, text) => g.append(el("text", { class: "fx-label", x: Math.min(x + 8, W - R - 230), y: Math.max(y - 8, 16) }, text));
  // 共用的互動：時長／幣別按鈕、滑過看數字、點一下留基準
  function wire(box, state, draw, show) {
    const svg = box.querySelector("svg"), tip = box.querySelector(".fx-tip");
    const at = (ev) => {
      const p = ev.touches ? ev.touches[0] : ev, r = svg.getBoundingClientRect();
      return state.index((p.clientX - r.left) / r.width * W);
    };
    const move = (ev) => { const i = at(ev); tip.textContent = show(svg.querySelector(".fx-hover"), i, state.ref); };
    svg.addEventListener("mousemove", move);
    svg.addEventListener("touchmove", move, { passive: true });
    svg.addEventListener("click", (ev) => { state.ref = at(ev); show(svg.querySelector(".fx-ref"), state.ref, null, true); move(ev); });
    box.addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-tab]");
      if (!b) return;
      state[b.closest("[data-tabs]").dataset.tabs.endsWith("range") ? "days" : "cur"] = b.dataset.tab;
      state.ref = null; draw(svg, tip);
    });
    draw(svg, tip);
  }
  const HINT = "滑過圖表看當天數字・點一下留下一條基準線，再滑到其他日期比較";

  // ---- 長期匯率 ----
  const lbox = document.getElementById("fx-long");
  if (lbox) {
    const s = { cur: lbox.querySelector('[data-tabs="fxcur"] .on').dataset.tab, days: lbox.querySelector('[data-tabs="fxrange"] .on').dataset.tab, ref: null };
    const H = 300, B = 24, T = 8;
    let pts, x, y;
    s.index = (px) => Math.max(0, Math.min(pts.length - 1, Math.round(px / (W - R) * (pts.length - 1))));
    const draw = (svg, tip) => {
      pts = since(data[s.cur].closes, +s.days);
      const vs = pts.map((r) => r[1]), lo = Math.min(...vs), hi = Math.max(...vs), span = hi - lo || 1, last = vs[vs.length - 1];
      x = (i) => i / (pts.length - 1) * (W - R);
      y = (v) => T + (hi - v) / span * (H - B - T * 2);
      svg.replaceChildren();
      hgrid(svg, lo, hi, y, 5, fmt);
      vticks(svg, pts.map((r) => r[0]), x, T, H - B, +s.days);
      svg.append(el("line", { class: "last", x1: 0, x2: W - R, y1: y(last), y2: y(last) }),
        el("polyline", { points: pts.map((r, i) => `${x(i).toFixed(1)},${y(r[1]).toFixed(1)}`).join(" ") }),
        el("g", { class: "fx-ref" }), el("g", { class: "fx-hover" }));
      tip.textContent = HINT;
      // 年化波動率：日對數報酬的標準差 × √252
      const rs = vs.slice(1).map((v, i) => Math.log(v / vs[i])), mean = rs.reduce((a, b) => a + b, 0) / rs.length;
      const vol = Math.sqrt(rs.reduce((a, b) => a + (b - mean) ** 2, 0) / (rs.length - 1) * 252) * 100;
      const chg = (last / vs[0] - 1) * 100, when = (v) => pts[vs.indexOf(v)][0];
      lbox.querySelector(".stats").innerHTML =
        tile("期間漲跌", `${chg > 0 ? "+" : ""}${chg.toFixed(2)}%`, `${pts[0][0]} ${fmt(vs[0])} → ${fmt(last)}`, tone(chg)) +
        tile("期間最高", fmt(hi), when(hi)) + tile("期間最低", fmt(lo), when(lo)) +
        tile("高低差", `${((hi / lo - 1) * 100).toFixed(1)}%`, "最高比最低多幾 %") +
        tile("年化波動率", `${vol.toFixed(1)}%`, "日漲跌的標準差 × √252");
    };
    const show = (g, i, ref, pin) => {
      const [d, v] = pts[i];
      g.replaceChildren(el("line", { class: "fx-cross", x1: 0, x2: W - R, y1: y(v), y2: y(v) }),
        el("line", { class: "fx-cross", x1: x(i), x2: x(i), y1: T, y2: H - B }), el("circle", { class: "fx-dot", cx: x(i), cy: y(v), r: 4 }));
      label(g, x(i), y(v), `${pin ? "基準 " : ""}${d}  ${fmt(v)}`);
      return ref == null ? `${d}　${fmt(v)}` : `${d}　${fmt(v)}　比基準（${pts[ref][0]} ${fmt(pts[ref][1])}）${pct(pts[ref][1], v)}`;
    };
    wire(lbox, s, draw, show);
  }

  // ---- 外資買賣超 vs 美元兌台幣：1 年內每日、3 年內每週、更長每月加總 ----
  const fbox = document.getElementById("fx-flows");
  if (fbox && data._flows && data["TWD=X"]) {
    const s = { days: fbox.querySelector('[data-tabs="flowrange"] .on').dataset.tab, ref: null };
    const H = 360, T = 8, MID = 170, L0 = 192, L1 = 330;  // 上半柱狀、下半折線
    const twd = new Map(data["TWD=X"].closes);
    let gs, x, yb, yl, unit;
    s.index = (px) => Math.max(0, Math.min(gs.length - 1, Math.floor(px / (W - R) * gs.length)));
    const bucket = (d) => {
      if (unit === "日") return d;
      if (unit === "月") return d.slice(0, 7);
      const t = new Date(d); t.setUTCDate(t.getUTCDate() - (t.getUTCDay() + 6) % 7);
      return t.toISOString().slice(0, 10);
    };
    const draw = (svg, tip) => {
      const days = +s.days;
      unit = days <= 365 ? "日" : days <= 1095 ? "週" : "月";
      const rows = since(data._flows, days);
      gs = [];
      let lastTwd = null;
      for (const [d, v] of rows) {
        if (twd.has(d)) lastTwd = twd.get(d);
        const k = bucket(d), g = gs[gs.length - 1];
        if (g && g.k === k) { g.v += v; g.n += 1; g.twd = lastTwd ?? g.twd; } else gs.push({ k, v, n: 1, twd: lastTwd, from: d });
      }
      const m = Math.max(...gs.map((g) => Math.abs(g.v))) || 1, ls = gs.filter((g) => g.twd != null).map((g) => g.twd);
      const lo = Math.min(...ls), hi = Math.max(...ls), span = hi - lo || 1, bw = (W - R) / gs.length;
      x = (i) => (i + 0.5) * bw;
      const zero = (T + MID) / 2;
      yb = (v) => zero - v / m * (zero - T);
      yl = (v) => L0 + (hi - v) / span * (L1 - L0);
      svg.replaceChildren();
      hgrid(svg, -m, m, yb, 3, (v) => `${Math.round(v).toLocaleString("en-US")} 億`);
      hgrid(svg, lo, hi, yl, 3, fmt);
      vticks(svg, gs.map((g) => g.from), x, T, L1, days);
      for (const [i, g] of gs.entries()) {
        const top = Math.min(yb(g.v), zero), h = Math.max(Math.abs(yb(g.v) - zero), 0.6);
        const bar = el("g", { class: g.v > 0 ? "up" : "down" });
        bar.append(el("rect", { x: x(i) - bw * 0.35, y: top, width: Math.max(bw * 0.7, 0.6), height: h }));
        svg.append(bar);
      }
      svg.append(el("polyline", { points: gs.map((g, i) => g.twd == null ? null : `${x(i).toFixed(1)},${yl(g.twd).toFixed(1)}`).filter(Boolean).join(" ") }),
        el("g", { class: "fx-ref" }), el("g", { class: "fx-hover" }));
      tip.textContent = `${unit === "日" ? "每日" : `每${unit}加總`}・${HINT}`;
      const sum = rows.reduce((a, r) => a + r[1], 0), buy = rows.filter((r) => r[1] > 0).length, sell = rows.filter((r) => r[1] < 0).length;
      const best = rows.reduce((a, r) => (r[1] > a[1] ? r : a)), worst = rows.reduce((a, r) => (r[1] < a[1] ? r : a));
      const flat = rows.length - buy - sell;
      fbox.querySelector(".stats").innerHTML =
        tile("期間外資累計", yi(Math.round(sum * 10) / 10), `${rows[0][0]} 起`, tone(sum)) +
        tile("買超／賣超天數", `${buy}／${sell}`, `共 ${rows.length} 個交易日${flat ? `、持平 ${flat} 天` : ""}`) +
        tile("最大單日買超", buy ? yi(best[1]) : "—", buy ? best[0] : "期間沒有買超日", buy ? "pos" : "") +
        tile("最大單日賣超", sell ? yi(worst[1]) : "—", sell ? worst[0] : "期間沒有賣超日", sell ? "neg" : "") +
        tile("美元兌台幣", ls.length ? `${ls[0] <= ls[ls.length - 1] ? "+" : ""}${((ls[ls.length - 1] / ls[0] - 1) * 100).toFixed(2)}%` : "—",
          ls.length ? `${fmt(ls[0])} → ${fmt(ls[ls.length - 1])}（正＝台幣轉弱）` : "");
    };
    const show = (g, i, ref, pin) => {
      const b = gs[i], name = unit === "週" ? `${b.k} 當週` : b.k;
      g.replaceChildren(el("line", { class: "fx-cross", x1: x(i), x2: x(i), y1: T, y2: L1 }));
      if (b.twd != null) g.append(el("line", { class: "fx-cross", x1: 0, x2: W - R, y1: yl(b.twd), y2: yl(b.twd) }), el("circle", { class: "fx-dot", cx: x(i), cy: yl(b.twd), r: 4 }));
      label(g, x(i), b.twd != null ? yl(b.twd) : L0, `${pin ? "基準 " : ""}${name}  外資 ${yi(Math.round(b.v * 10) / 10)}  台幣 ${b.twd != null ? fmt(b.twd) : "—"}`);
      let text = `${name}　外資 ${yi(Math.round(b.v * 10) / 10)}${unit === "日" ? "" : `（${unit}合計）`}　美元兌台幣 ${b.twd != null ? fmt(b.twd) : "—"}`;
      if (ref != null && ref !== i) {
        const [a, z] = ref < i ? [ref, i] : [i, ref], cum = gs.slice(a + 1, z + 1).reduce((t, x) => t + x.v, 0);
        text += `　｜比基準（${gs[ref].k}）：外資累計 ${yi(Math.round((ref < i ? cum : -cum) * 10) / 10)}`;
        if (b.twd != null && gs[ref].twd != null) text += `、美元兌台幣 ${pct(gs[ref].twd, b.twd)}`;
      }
      return text;
    };
    wire(fbox, s, draw, show);
  }
})();
</script>"""


def long_chart(hist: dict | None) -> str:
    """匯率長期走勢：選幣別、選時長；有日期刻度、價格虛線，滑過看當天價格、點一下留基準線比較。"""
    if not hist:
        return '<p class="empty">長期資料暫時讀不到</p>'
    keys = [t for t, *_ in PAIRS if t in hist]
    if not keys:
        return '<p class="empty">長期資料暫時讀不到</p>'
    return (f'<div id="fx-long">{tabs("fxcur", [(t, hist[t]["name"]) for t in keys], keys[0])} {tabs("fxrange", RANGES, "1095")}'
            '<div class="mk-chart"><svg class="mk-candles fx-long-svg" viewBox="0 0 1000 300" role="img" aria-label="匯率長期走勢"></svg>'
            '<p class="mk-note fx-tip"></p></div><div class="stats"></div></div>')


def flows_chart(hist: dict | None, m: dict) -> str:
    """外資買賣超 vs 美元兌台幣：選時長；10 年資料（fx_history.json）再補上 history.json 最新幾天。"""
    if not (hist or {}).get("_flows") or "TWD=X" not in hist:
        return '<p class="empty">資料暫時讀不到</p>'
    return (f'<div id="fx-flows">{tabs("flowrange", RANGES, "365")}'
            '<div class="mk-chart"><svg class="mk-candles fx-long-svg" viewBox="0 0 1000 360" role="img" aria-label="外資買賣超與美元兌台幣"></svg>'
            '<p class="mk-note fx-tip"></p></div><div class="stats"></div></div>')


def chart_data(hist: dict | None, m: dict) -> str:
    """兩張圖共用的資料（放在頁面裡一次）。"""
    if not hist:
        return ""
    flows = dict(hist.get("_flows") or [])
    flows.update({h["date"]: h["foreign"] for h in m.get("history") or [] if h.get("foreign") is not None})
    data = {**hist, "_flows": sorted(flows.items())}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/json" id="fx-long-data">{blob}</script>{CHART_SCRIPT}'


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
        "值得一提的連動（相關係數絕對值 ≥ 0.2）": {f'{c["fx"]} vs {c["stock"]}': f'{c["r"]:+.2f}：{describe(c)}' for c in cs if abs(c["r"]) >= 0.2},
    }


PROMPT = """你是財經網站的編輯。依下面 JSON 資料，寫 2 到 3 句「匯率對台股、日股、歐股、美股可能帶來的影響」。
語氣直接，繁體中文，150 字以內。
規則：
- 只能用資料裡出現的數字，不要自己計算新數字，也不要補充資料以外的事實
- 相關係數是過去的統計，不要寫成會發生的事；不預測漲跌，不給買賣建議，不提目標價
- 相關係數絕對值小於 0.2 的不要個別提，最多一句「其他匯率和股市幾乎沒有連動」帶過
- 一定要寫到：「外資近5日買賣超合計」對台幣與台股的意義，以及「值得一提的連動」裡的每一項
- 「影響」要點名具體對象（例如出口電子股、進口業者、外資、美國科技股）
- 匯率方向：「美元兌台幣」「100 日圓兌台幣」「歐元兌台幣」是 1 單位外幣換多少台幣，數字下跌＝台幣升值、外幣走弱；數字上升＝台幣貶值、外幣走強
- 不要逐一複述每個匯率的收盤價和漲跌
回傳 JSON：{{"text": "那幾句話"}}

資料：
{data}"""


def ai_view(f: dict) -> str:
    """沒有金鑰、失敗或沒通過檢查就回空字串（整段不顯示）。"""
    from discord_push import GROQ_KEY, ask_groq, has_banned, numbers_ok

    if not GROQ_KEY():
        return ""
    data = json.dumps(f, ensure_ascii=False)
    for _ in range(2):  # 沒通過檢查就重寫一次（一天只產生一次，多問一次不貴）
        try:
            text = str(ask_groq(PROMPT.format(data=data)).get("text") or "").strip()
        except Exception as exc:  # noqa: BLE001 — AI 失敗不能讓整個建站失敗
            print(f"⚠️ 匯率 AI 解讀失敗：{exc}", file=sys.stderr)
            return ""
        if text and len(text) <= 300 and not has_banned(text) and numbers_ok(text, data + " 0.2"):  # 0.2 是提示詞裡的門檻
            return text
        print(f"⚠️ 匯率 AI 解讀沒通過檢查：{text}", file=sys.stderr)
    return ""


def refresh_ai(m: dict, path: Path) -> None:
    """台北 15:30 後（台股收盤資料齊了）每天最多試一次；失敗就沿用舊的一段，當天不再重試。"""
    from discord_push import GROQ_KEY

    if not GROQ_KEY():
        path.unlink(missing_ok=True)  # 拿掉金鑰＝不要 AI 解讀，舊的那段也一起拿掉
        return
    now = datetime.now(timezone(timedelta(hours=8)))
    today = now.date().isoformat()
    if now.strftime("%H%M") < "1530":
        return  # 收盤資料還沒齊，不寫盤中的解讀
    old = read_json(path)
    if old.get("date") == today:
        return
    text = ai_view(facts(m, correlations(m) + correlations(m, HEDGE)))
    write_json(path, {"date": today, "text": text or old.get("text", ""), "made": today if text else old.get("made")})


def render(m: dict | None, hero, section, hist: dict | None = None, ai: dict | None = None) -> str:
    fx = [i for i in (m or {}).get("indices") or [] if i["region"] == "匯率"]
    if not fx:
        return hero("匯率", "匯率資料準備中", "下一次網站更新後就會出現。")
    cs, hedge = correlations(m), correlations(m, HEDGE)
    body = hero("匯率", "台幣跟著誰走", f"台幣兌美元、日圓、歐元的走勢，以及匯率和各地股市的連動・資料日 {e(fx[0]['date'])}")
    body += '<main class="wrap">'
    body += section("匯率走勢", index_board(fx, "fx"), '<span class="live-dot"></span><span class="live-stamp">盤中即時更新</span>・點卡片看近半年日 K・台幣匯率數字越大＝台幣越弱')
    body += section("長期走勢", long_chart(hist), "選幣別與時長・最長近 10 年日收盤")
    if (ai or {}).get("text"):
        body += section("AI 解讀", f'<p>{e(ai["text"])}</p>', f'{e(ai.get("made") or "")} 依當時數字整理・每天收盤後更新・僅供學習研究，不構成投資建議')
    body += section("匯率與股市連動", corr_table(cs), "美元／台幣 vs 台股・100 日圓／台幣 vs 日經・歐元／台幣 vs 歐洲 STOXX 50・美元指數 vs S&P 500")
    body += section("避險情緒", corr_table(hedge, ("恐慌指標", "匯率")), "市場緊張時，資金常流向日圓、美元：看 VIX 上升的日子，日圓、美元是否同步走強")
    body += section("外資進出 vs 台幣", flows_chart(hist, m), "上：外資買賣超（上市，億元）・下：美元兌台幣收盤・最長近 10 年")
    return body + "</main>" + TAB_SCRIPT + chart_data(hist, m)
