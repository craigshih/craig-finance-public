// 選股機器人（「幫我找股票」）：把使用者的情境變成條件，再用固定規則從每日資料裡挑出研究候選。
// 分工：AI 只負責兩件事——把一句話翻成條件（SPEC），以及替挑出來的股票寫理由；
// 「挑哪幾檔」完全由下面的規則決定，AI 不能自己加股票、也不能自己補數字。

export const MAX_PICKS = 8;
export const DEFAULT_PICKS = 5;

const isCommon = (code) => /^[1-9]\d{3}$/.test(code);
const isEtf = (code) => /^00\d{2,4}[A-Z]?$/.test(code);

// 給 AI 的可選清單：證交所產業別、供應鏈族群
export function vocab(stocks) {
  const industries = new Set(), themes = new Set();
  for (const s of Object.values(stocks)) {
    if (s.industry && isCommon(s.code)) industries.add(s.industry);
    for (const p of s.peers || []) if (p.group) themes.add(p.group);
  }
  return { industries: [...industries].sort(), themes: [...themes].sort() };
}

export function specPrompt(question, v) {
  return `把使用者的選股情境翻成篩選條件。只輸出 JSON，不要解釋。
可用的產業別（只能從這裡選，可複選）：${v.industries.join("、")}
可用的供應鏈族群（只能從這裡選，可複選）：${v.themes.join("、")}

JSON 格式：
{
  "industries": [],      // 使用者提到的產業，例如「金融股」→ 金融保險業；「半導體」→ 半導體業
  "themes": [],          // 使用者提到的題材族群
  "names": [],           // 使用者點名的公司（照原文寫，例如「聯發科」「日月光」）
  "leaders": false,      // 想要龍頭、大型、權值股
  "dip": false,          // 想趁大跌、拉回、跌深時找標的
  "dividend": false,     // 重視配息、存股、高殖利率
  "value": false,        // 想要便宜、低本益比
  "growth": false,       // 想要成長、營收成長快
  "low_risk": false,     // 想要穩健、波動小
  "etf": false,          // 想看 ETF
  "count": 5,            // 想看幾檔（3～8，沒說就 5）
  "intent": "用一句話重述使用者想找什麼（30 字內）"
}

使用者：${question}`;
}

const bool = (x) => x === true;
export function cleanSpec(raw, v) {
  const inSet = (xs, set) => (Array.isArray(xs) ? xs : []).map(String).filter((x) => set.includes(x));
  const n = Number(raw?.count);
  return {
    industries: inSet(raw?.industries, v.industries),
    themes: inSet(raw?.themes, v.themes),
    names: (Array.isArray(raw?.names) ? raw.names : []).map((x) => String(x).slice(0, 12)).slice(0, 6),
    leaders: bool(raw?.leaders), dip: bool(raw?.dip), dividend: bool(raw?.dividend), value: bool(raw?.value),
    growth: bool(raw?.growth), low_risk: bool(raw?.low_risk), etf: bool(raw?.etf),
    count: Number.isFinite(n) ? Math.min(MAX_PICKS, Math.max(3, Math.round(n))) : DEFAULT_PICKS,
    intent: String(raw?.intent || "").slice(0, 60),
  };
}

// 百分位（0～1）：在候選裡的相對位置
function ranker(rows, get) {
  const xs = rows.map(get).filter((x) => x != null && Number.isFinite(x)).sort((a, b) => a - b);
  return (r) => {
    const x = get(r);
    if (x == null || !Number.isFinite(x) || !xs.length) return 0.5;
    let lo = 0;
    while (lo < xs.length && xs[lo] <= x) lo++;
    return lo / xs.length;
  };
}

// 產業內市值排名（1＝龍頭）
export function industryRanks(stocks) {
  const by = {};
  for (const s of Object.values(stocks)) if (isCommon(s.code) && s.industry && s.mcap_yi) (by[s.industry] ||= []).push(s);
  const rank = {};
  for (const list of Object.values(by)) list.sort((a, b) => b.mcap_yi - a.mcap_yi).forEach((s, i) => { rank[s.code] = i + 1; });
  return rank;
}

const chg20 = (s) => s.risk?.chg_20d ?? null;
const chg5 = (s) => s.risk?.chg_5d ?? null;
// 「跌深」：近 5 日與近 20 日跌幅各半（大跌常集中在最近幾天）
const drop = (s) => (chg20(s) == null || chg5(s) == null ? null : -(chg5(s) + chg20(s)) / 2);

// 依條件挑股：回傳 [{code, score, reasons: [...規則面的理由]}]
export function pickStocks(stocks, spec, mentioned = [], opts = {}) {
  const rank = industryRanks(stocks);
  const themeOf = (s) => new Set((s.peers || []).map((p) => p.group));
  let pool = Object.values(stocks).filter((s) => s.close && (spec.etf ? isEtf(s.code) : isCommon(s.code)));
  const scoped = spec.industries.length || spec.themes.length;
  // 使用者點名的公司：同產業也一起納入比較
  const mentionedInd = new Set(mentioned.map((c) => stocks[c]?.industry).filter(Boolean));
  if (scoped || mentioned.length) {
    pool = pool.filter((s) => spec.industries.includes(s.industry) || spec.themes.some((t) => themeOf(s).has(t))
      || mentioned.includes(s.code) || (!scoped && mentionedInd.has(s.industry)));
  }
  // 基本體質：有獲利（本益比為正）；ETF 不檢查。金融股沒有月營收檔，所以不要求營收資料
  if (!spec.etf) pool = pool.filter((s) => s.valuation?.pe > 0 || mentioned.includes(s.code));
  if (spec.leaders && !spec.etf) pool = pool.filter((s) => (rank[s.code] || 99) <= 3 || mentioned.includes(s.code));
  if (spec.dip) pool = pool.filter((s) => chg20(s) != null || mentioned.includes(s.code)); // 要有近期漲跌資料才能判斷跌深
  if (opts.priced) pool = pool.filter((s) => opts.priced.has(s.code) || mentioned.includes(s.code));
  if (!pool.length) return [];

  const P = {
    size: ranker(pool, (s) => s.mcap_yi), drop: ranker(pool, drop),
    roe: ranker(pool, (s) => s.valuation?.roe_est), gross: ranker(pool, (s) => s.margins?.gross),
    cheap: ranker(pool, (s) => (s.valuation?.pe > 0 ? -s.valuation.pe : null)), yld: ranker(pool, (s) => s.valuation?.yield),
    rev: ranker(pool, (s) => s.revenue?.yoy), calm: ranker(pool, (s) => (s.risk?.vol_1y == null ? null : -s.risk.vol_1y)),
    flow: ranker(pool, (s) => s.factors?.trust_buy),
  };
  const scored = pool.map((s) => {
    const w = [
      [P.size(s), spec.leaders ? 2 : 0.5], [P.roe(s), 1], [P.gross(s), 0.5], [P.flow(s), 0.3],
      [P.drop(s), spec.dip ? 1.5 : 0], [P.cheap(s), spec.value ? 1.5 : 0.3], [P.yld(s), spec.dividend ? 1.5 : 0.2],
      [P.rev(s), spec.growth ? 1.5 : 0.4], [P.calm(s), spec.low_risk ? 1.2 : 0],
    ];
    let score = w.reduce((a, [x, k]) => a + x * k, 0) / w.reduce((a, [, k]) => a + k, 0);
    // 跌深但營收也大幅衰退：可能是基本面轉壞，不是單純被大盤拖累
    if (spec.dip && (s.revenue?.yoy ?? 0) < -20) score -= 0.15;
    if (mentioned.includes(s.code)) score += 0.05;
    const reasons = [];
    if ((rank[s.code] || 99) <= 3 && !spec.etf) reasons.push(`${s.industry}市值第 ${rank[s.code]} 大`);
    const sg = (x) => `${x > 0 ? "+" : ""}${x}%`;
    if (spec.dip && chg20(s) != null) reasons.push(`近 5 日 ${sg(chg5(s))}・近 20 日 ${sg(chg20(s))}`);
    if (spec.dividend && s.valuation?.yield) reasons.push(`殖利率 ${s.valuation.yield}%`);
    if (spec.value && s.valuation?.pe) reasons.push(`本益比 ${s.valuation.pe}`);
    if (spec.growth && s.revenue?.yoy != null) reasons.push(`月營收年增 ${s.revenue.yoy}%`);
    if (spec.low_risk && s.risk?.vol_1y != null) reasons.push(`年化波動 ${s.risk.vol_1y}%`);
    if (mentioned.includes(s.code)) reasons.push("你點名的");
    return { code: s.code, score: Math.round(score * 1000) / 1000, reasons, rank: rank[s.code] || null };
  }).sort((a, b) => b.score - a.score);

  // 分散：同一產業最多 2 檔（使用者只選一個產業時不限）
  const singleInd = spec.industries.length === 1 && !spec.themes.length
    && mentioned.every((c) => stocks[c]?.industry === spec.industries[0]);
  const perInd = {}, out = [];
  for (const r of scored) {
    const ind = stocks[r.code].industry || "其他";
    if (!singleInd && (perInd[ind] || 0) >= 2 && !mentioned.includes(r.code)) continue;
    perInd[ind] = (perInd[ind] || 0) + 1;
    out.push(r);
    if (out.length >= spec.count) break;
  }
  return out;
}

export const EXPLAIN_PROMPT = `你是台股研究助理。使用者描述了一個選股情境，系統已經依固定規則挑出幾檔「研究候選」（DATA.picks）。
請替每一檔寫出它為什麼符合使用者的情境，以及需要留意的地方。

規則：
1. 只能使用 DATA 裡的數字與事實；DATA 沒有的就不要寫。公司一律用中文名稱。
2. 這些是「研究候選」，不是買進建議。不要寫目標價、不要預測股價、不要說保證或一定會漲。
3. 使用者想趁大跌進場時，要提醒：大跌時可能還會再跌、可以分批、單一個股不要占太多資金，並看這檔跌深是因為大盤還是公司本身（例如營收衰退）。
4. 輸出 JSON：
{
  "intro": "一句話說明這次怎麼挑（40 字內）",
  "picks": [{"code": "代號", "why": "為什麼符合情境（80 字內，引用 DATA 數字）", "watch": "要留意什麼（50 字內）"}],
  "cautions": ["整體提醒（每點 40 字內，2～3 點）"]
}`;
