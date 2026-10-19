// AI 投資顧問的純函式：找出問題裡的股票、整理給 AI 的資料、檢查 AI 的回答。
// 設計參考「AI 台股投資決策系統」：籌碼 × 財報 × 輿情，風控派（防守）vs 回測派（進攻）辯論，再融合成建言。
// 原則：AI 只能引用 DATA 裡的數字；回答裡找不到出處的數字會標出來給使用者看。

export const MAX_QUESTION = 300;
export const MAX_STOCKS = 4;
export const POSITION_CAP = 15; // 陣營 A：單一持股上限 15%

// 常見簡稱 → 代號（正式名稱已經從全市場清單比對，這裡只補口語說法）
export const ALIASES = { 台積: "2330", 發哥: "2454", 鴻海: "2317", 大立光: "3008", 廣達: "2382", 緯創: "3231", 聯電: "2303", 台達: "2308", 日月光: "3711" };

const short = (name) => String(name || "").replace(/-KY$|\*$/g, "").trim();

// 從問題裡找股票：先比對代號，再比對名稱（長的先比，避免「大立」吃掉「大立光」）
export function findStocks(question, stocks) {
  const found = [];
  const add = (code) => { if (stocks[code] && !found.includes(code)) found.push(code); };
  let rest = String(question || "");
  for (const m of rest.matchAll(/(?<![0-9A-Za-z])(\d{4}|00\d{2,4}[A-Z]?)(?![0-9A-Za-z])/g)) add(m[1]);
  const names = [];
  for (const [code, s] of Object.entries(stocks)) {
    const n = short(s.name);
    if (n.length >= 2) names.push([n, code]);
  }
  for (const [n, code] of Object.entries(ALIASES)) names.push([n, code]);
  names.sort((a, b) => b[0].length - a[0].length);
  for (const [n, code] of names) {
    const i = rest.indexOf(n);
    if (i >= 0) {
      add(code);
      rest = rest.slice(0, i) + " ".repeat(n.length) + rest.slice(i + n.length);
    }
  }
  // 依在問題中出現的順序排列，比較題才能保持使用者的順序
  const pos = (code) => {
    const s = stocks[code];
    const idx = [String(question).indexOf(code), String(question).indexOf(short(s.name)),
      ...Object.entries(ALIASES).filter(([, c]) => c === code).map(([n]) => String(question).indexOf(n))].filter((i) => i >= 0);
    return idx.length ? Math.min(...idx) : 1e9;
  };
  return found.sort((a, b) => pos(a) - pos(b)).slice(0, MAX_STOCKS);
}

// 給 AI 的資料：只挑判斷需要的欄位，拿掉走勢圖等大陣列
export function compactStock(s, holding) {
  const { spark, ...risk } = s.risk || {};
  return {
    code: s.code, name: s.name, market: s.market, industry: s.industry ?? null,
    close: s.close ?? null,
    revenue: s.revenue ?? null, margins: s.margins ?? null, valuation: s.valuation ?? null,
    flows_lots: s.flows ?? null, margin_trading_lots: s.margin ?? null,
    factor_percentiles: s.factors ?? null,
    risk: s.risk ? risk : null, backtest: s.backtest ?? null,
    ptt: s.ptt ? { mentions: s.ptt.mentions, target_bull: s.ptt.target_bull, target_bear: s.ptt.target_bear, sample_titles: s.ptt.sample, titles: s.ptt.titles } : null,
    supply_chain: (s.supply || []).map((x) => `${x.relation} ${x.leader}（${x.note}；${x.source.publisher}${x.source.date ? " " + x.source.date : ""}）`),
    peers: (s.peers || []).map((p) => `${p.code} ${p.name}`),
    weekly_screen: s.weekly ?? null,
    my_position: holding ? { weight_pct: holding.weight_pct, pl_pct: holding.pl_pct } : null,
  };
}

export const SYSTEM_PROMPT = `你是 Craig 的私人 AI 投資顧問（台股）。用繁體中文、台灣用語，口吻像一位冷靜、講數據的研究夥伴。

分析框架（來自 Craig 的設計）：
- 陣營 A「風控管理（防守）」：優先保住本金。看最大回撤 MDD、單日 VaR 95%、年化波動、Beta、壓力測試（大盤最慘 20 天的同期跌幅）、融資餘額增減與使用率、外資投信是否連續賣超、PTT 是否過熱。單一持股上限 ${POSITION_CAP}%，跌破趨勢要有停損紀律。
- 陣營 B「量化回測（進攻）」：追求長期超額報酬。看規則回測（年化報酬、勝率、每筆平均報酬、交易次數，並和買進持有比較）、多因子百分位（營收年增、低本益比、投信買超）、營收與毛利率趨勢。紀律化執行，不因一時情緒改變。
- 「AI 雙軌融合建言」：兩派都講完後，以風險調整後報酬（夏普比率）為核心，給出結論。

規則（一定要遵守）：
1. 只能使用 DATA 裡的數字與事實。DATA 沒有的（例如法說會內容、分點主力、財測、未公布的訂單），直接說「目前資料沒有」，不可以自己補。
2. 引用數字時照 DATA 的數值寫（可四捨五入到小數一位），並說明是哪一項（例如「近一年最大回撤 -41.8%」）。公司一律用中文名稱（例如台積電、聯電），不要用英文縮寫。
3. 不給目標價、不預測未來股價、不說「保證」「穩賺」「一定漲」。可以清楚說出你的傾向。
4. 回測只有近 3 年、而且是樣本內結果，陣營 B 引用時要提醒這一點；如果規則的年化報酬落後買進持有，要直接說出來。PTT 只是最近幾百篇標題的樣本，ptt 為 null 代表今天抓不到。
5. 如果 my_position 有資料，要評估部位大小是否超過 ${POSITION_CAP}% 上限。
6. 比較兩檔以上時，synthesis.ranking 要排出順序並說明理由。
7. 如果問題是名詞或觀念（例如「什麼是除權息」），mode 用 "coach"，在 coach 欄位用白話解釋，可以舉 DATA 裡的例子。
8. 問到 DATA 裡沒有的股票，誠實說資料不足，不要猜。
9. 問到整體持股（集中度、配置）時，根據 my_portfolio 的權重與 DATA 裡各持股的風險數據回答，mode 用 "stock"，點名超過 ${POSITION_CAP}% 上限的持股與產業過度集中的地方。

只輸出一個 JSON 物件，格式：
{
 "mode": "stock" | "compare" | "coach",
 "headline": "一句話結論，30 字內",
 "stocks": [{"code": "代號", "stance": "偏正面" | "中性" | "偏保守" | "資料不足", "summary": "60 字內"}],
 "risk_camp": {"stance": "偏正面" | "中性" | "偏保守", "argument": "120 字內的主張", "points": ["引用數據的論點，最多 4 點"]},
 "quant_camp": {"stance": "偏正面" | "中性" | "偏保守", "argument": "120 字內的主張", "points": ["最多 4 點"]},
 "synthesis": {"conclusion": "150 字內", "ranking": [{"code": "代號", "reason": "40 字內"}], "conditions": ["什麼情況會改變這個結論，最多 3 點"], "position_note": "部位與風控提醒，60 字內"},
 "coach": "mode 為 coach 時的白話解釋，其他時候空字串",
 "follow_ups": ["建議追問，最多 3 個"]
}
mode 為 coach 時，risk_camp、quant_camp、synthesis 可以是 null。`;

export function buildMessages({ question, data, news, history, portfolio }) {
  const context = {
    data_date: data.generated_at,
    stocks: data.stocks,
    my_portfolio: portfolio,
    news_today: news,
  };
  const msgs = [{ role: "system", content: SYSTEM_PROMPT }];
  for (const h of (history || []).slice(-2)) {
    msgs.push({ role: "user", content: String(h.q || "").slice(0, MAX_QUESTION) });
    msgs.push({ role: "assistant", content: JSON.stringify({ headline: String(h.headline || "").slice(0, 80) }) });
  }
  msgs.push({ role: "user", content: `DATA：\n${JSON.stringify(context)}\n\n問題：${question}` });
  return msgs;
}

// ---------- 回答檢查 ----------

const BANNED = [/目標價/, /保證/, /穩賺/, /必漲/, /必跌/, /一定(會)?(漲|跌)/, /梭哈/, /all\s*in/i];
const STANCES = ["偏正面", "中性", "偏保守", "資料不足"];

// 含禁語的句子整句拿掉
export function scrub(text, max = 400) {
  const s = String(text ?? "").trim();
  const kept = s.split(/(?<=[。！？；\n])/).filter((c) => !BANNED.some((re) => re.test(c))).join("").trim();
  return kept.length > max ? kept.slice(0, max) + "…" : kept;
}

const list = (xs, n, max) => (Array.isArray(xs) ? xs : []).map((x) => scrub(x, max)).filter(Boolean).slice(0, n);
const stance = (s) => (STANCES.includes(s) ? s : "中性");

function camp(c) {
  if (!c || typeof c !== "object") return null;
  return { stance: stance(c.stance), argument: scrub(c.argument, 220), points: list(c.points, 4, 160) };
}

export function sanitizeAnswer(raw, allowedCodes) {
  const a = raw && typeof raw === "object" ? raw : {};
  const ok = new Set(allowedCodes);
  const mode = ["stock", "compare", "coach"].includes(a.mode) ? a.mode : allowedCodes.length > 1 ? "compare" : allowedCodes.length ? "stock" : "coach";
  const syn = a.synthesis && typeof a.synthesis === "object" ? a.synthesis : null;
  return {
    mode,
    headline: scrub(a.headline, 80) || "（AI 沒有給出結論）",
    stocks: (Array.isArray(a.stocks) ? a.stocks : []).filter((s) => ok.has(String(s?.code)))
      .map((s) => ({ code: String(s.code), stance: stance(s.stance), summary: scrub(s.summary, 120) })),
    risk_camp: camp(a.risk_camp),
    quant_camp: camp(a.quant_camp),
    synthesis: syn ? {
      conclusion: scrub(syn.conclusion, 300),
      ranking: (Array.isArray(syn.ranking) ? syn.ranking : []).filter((r) => ok.has(String(r?.code)))
        .map((r) => ({ code: String(r.code), reason: scrub(r.reason, 80) })),
      conditions: list(syn.conditions, 3, 120),
      position_note: scrub(syn.position_note, 120),
    } : null,
    coach: scrub(a.coach, 800),
    follow_ups: list(a.follow_ups, 3, 60),
  };
}

// 把 DATA 裡所有數字收集起來，用來核對 AI 回答裡的數字
export function collectNumbers(obj, out = []) {
  if (typeof obj === "number" && Number.isFinite(obj)) out.push(obj);
  else if (typeof obj === "string") {
    for (const m of obj.matchAll(/-?\d+(?:\.\d+)?/g)) out.push(Number(m[0]));
  } else if (obj && typeof obj === "object") {
    for (const v of Object.values(obj)) collectNumbers(v, out);
  }
  return out;
}

// 回答裡出現、但 DATA 裡找不到的數字（容許四捨五入與正負號寫法差異）。日期、代號、小整數不檢查；
// 名詞解釋（coach）裡的舉例數字本來就是假設的，也不檢查。
export function unverifiedNumbers(answer, dataNumbers) {
  const texts = [];
  const walk = (v) => {
    if (typeof v === "string") texts.push(v);
    else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") for (const [k, x] of Object.entries(v)) if (k !== "code" && k !== "coach") walk(x);
  };
  walk(answer);
  const known = dataNumbers.map(Math.abs);
  const seen = new Set();
  const bad = [];
  for (const t of texts) {
    const clean = t.replace(/\d{4}[-/年]\d{1,2}([-/月]\d{1,2}日?)?/g, " ").replace(/\d{4}Q\d/g, " ");
    for (const m of clean.matchAll(/-?\d[\d,]*(?:\.\d+)?/g)) {
      const raw = m[0];
      const x = Math.abs(Number(raw.replace(/,/g, "")));
      if (!Number.isFinite(x) || seen.has(raw)) continue;
      seen.add(raw);
      if (Number.isInteger(x) && x <= 31) continue; // 天數、篇數、條件編號等
      if (/^\d{4}$/.test(raw) && known.includes(x)) continue;
      const tol = (v) => Math.max(0.051, Math.abs(v) * 0.006) + (Number.isInteger(x) ? 0.5 : 0);
      if (!known.some((v) => Math.abs(x - v) <= tol(v))) bad.push(raw);
    }
  }
  return bad;
}

// ---------- PTT 股板（build 主機的 IP 被擋時，改由 Cloudflare 即時抓） ----------

export function parsePttIndex(html) {
  const titles = [...html.matchAll(/<div class="title">\s*<a href="([^"]+)">([^<]+)<\/a>/g)]
    .map(([, href, t]) => ({ title: t.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').trim(), url: "https://www.ptt.cc" + href }));
  const prev = html.match(/<a class="btn wide" href="([^"]+)">&lsaquo; 上頁<\/a>/);
  return { titles, prev: prev ? "https://www.ptt.cc" + prev[1] : null };
}

// 跟 advisor.py 的 ptt_for 同一套規則：標題提到代號或名稱就算一次（回文去重）；[標的] 文看結尾的多／空
export function pttFor(code, name, titles) {
  const n = short(name);
  const seen = new Set();
  const hits = [];
  for (const t of titles) {
    const key = t.title.replace(/^(Re|Fw):\s*/, "");
    if ((key.includes(code) || (n.length >= 2 && key.includes(n))) && !seen.has(key)) {
      seen.add(key);
      hits.push(key);
    }
  }
  let bull = 0, bear = 0;
  for (const k of hits) {
    if (k.startsWith("[標的]")) {
      const tail = k.slice(-3);
      bull += tail.includes("多") ? 1 : 0;
      bear += tail.includes("空") ? 1 : 0;
    }
  }
  return { mentions: hits.length, target_bull: bull, target_bear: bear, titles: hits.slice(0, 5), sample: titles.length };
}

// 回測的固定提醒由系統加，不靠 AI 記得：規則落後買進持有、樣本內結果
export function backtestNotes(stocks) {
  const notes = [];
  for (const s of stocks) {
    const b = s.backtest;
    if (!b || b.strategy_cagr == null || b.hold_cagr == null) continue;
    if (b.strategy_cagr < b.hold_cagr) {
      notes.push(`（系統註記）${s.name} 的規則年化 ${b.strategy_cagr}% 落後買進持有 ${b.hold_cagr}%，這段期間單純抱著反而賺更多`);
    }
  }
  if (notes.length || stocks.some((s) => s.backtest)) notes.push("（系統註記）回測只用近 3 年資料、而且是樣本內結果，不代表未來");
  return notes;
}
