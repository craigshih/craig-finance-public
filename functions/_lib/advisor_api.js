// AI 投資顧問的共用處理：站長版（/portfolio/api/advisor，帶持股）與訪客版（/robot/api/advisor，不帶持股）。
// 資料：build 時產生的 stocks.json（每日）、站長版另有 holdings.json（持股權重），加上鉅亨網即時新聞。

import {
  MAX_QUESTION, MAX_STOCKS, backtestNotes, buildMessages, collectNumbers, compactStock, findStocks, parsePttIndex, pttFor, sanitizeAnswer,
  unverifiedNumbers,
} from "./advisor.js";
import { parseRss } from "../api/news.js";

const MODEL = "openai/gpt-oss-120b";
const UA = "craig-finance-hub/1.0 (+https://github.com/craigshih)";
const PROMPT_NUMBERS = [15, 300, 60, 120, 20, 95, 52, 1.5, 3];
const memo = {};

const fail = (error, status = 400) => Response.json({ error }, { status });

export async function asset(env, request, path) {
  // 帶上登入 cookie：靜態檔也在密碼保護範圍內
  const res = await env.ASSETS.fetch(new Request(new URL(path, request.url), { headers: { Cookie: request.headers.get("Cookie") || "" } }));
  if (!res.ok || !(res.headers.get("Content-Type") || "").includes("json")) return null; // 沒有這個檔時可能回 HTML 頁
  return res.json().catch(() => null);
}

export async function loadData(env, request, dataPath, holdingsPath) {
  const m = memo[dataPath];
  if (m?.data && Date.now() - m.at < 10 * 60_000) return m;
  const [data, holdings] = await Promise.all([
    asset(env, request, dataPath),
    holdingsPath ? asset(env, request, holdingsPath) : null,
  ]);
  if (data) memo[dataPath] = { at: Date.now(), data, holdings };
  return { data, holdings };
}

// 鉅亨網即時新聞裡，標題點名這幾檔的（只用標題，不改寫內容）
async function relatedNews(stocks) {
  const feeds = ["tw_stock", "headline"];
  const items = (await Promise.all(feeds.map(async (f) => {
    try {
      const res = await fetch(`https://news.cnyes.com/rss/v1/news/category/${f}`, { headers: { "User-Agent": UA } });
      return res.ok ? parseRss(await res.text(), f) : [];
    } catch {
      return [];
    }
  }))).flat();
  const out = {};
  for (const s of stocks) {
    const n = s.name.replace(/-KY$|\*$/, "");
    const seen = new Set();
    out[s.code] = items.filter((i) => (i.title.includes(n) || i.title.includes(s.code)) && !seen.has(i.url) && seen.add(i.url))
      .slice(0, 4).map((i) => ({ title: i.title, url: i.url, time: i.time }));
  }
  return out;
}

// PTT 股板最新 6 頁標題，15 分鐘共用一次
let pttMemo = { at: 0, titles: null };
async function pttTitles() {
  if (pttMemo.titles && Date.now() - pttMemo.at < 15 * 60_000) return pttMemo.titles;
  const titles = [];
  let url = "https://www.ptt.cc/bbs/Stock/index.html";
  try {
    for (let i = 0; i < 6 && url; i++) {
      const res = await fetch(url, { headers: { "User-Agent": UA } });
      if (!res.ok) break;
      const page = parsePttIndex(await res.text());
      titles.push(...page.titles);
      url = page.prev;
    }
  } catch (exc) {
    console.error("ptt", exc);
  }
  if (titles.length) pttMemo = { at: Date.now(), titles };
  return titles;
}

// json=false 時回傳純文字 { text, tokens }（LINE 機器人聊天用）
export async function askGroq(env, messages, { max = 3500, effort = "medium", json = true, temperature = 0.3, model = MODEL } = {}) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.GROQ_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model, messages, max_completion_tokens: max, reasoning_effort: effort,
        temperature, ...(json ? { response_format: { type: "json_object" } } : {}),
      }),
    });
    if (res.status === 429 && attempt === 0) {
      await new Promise((r) => setTimeout(r, 4000));
      continue;
    }
    if (!res.ok) throw new Error(`Groq ${res.status}: ${(await res.text()).slice(0, 200)}`);
    const body = await res.json();
    const content = body.choices[0].message.content;
    const tokens = body.usage?.total_tokens || 0;
    return json ? { raw: JSON.parse(content), tokens } : { text: String(content || "").trim(), tokens };
  }
  throw new Error("Groq 忙線中");
}

// opts：{ dataPath, holdingsPath（訪客版為 null）, guest（true 時不寫入 advisor_watch）,
//         beforeAsk（額度檢查，回傳錯誤 Response 或 null）, afterAsk(tokens)（記錄用量） }
export async function handleAdvisor({ request, env }, opts) {
  let body;
  try {
    body = await request.json();
  } catch {
    return fail("格式不正確");
  }
  const r = await advise({ request, env }, { question: body?.question, history: body?.history }, opts);
  return r.blocked || Response.json(r.body, { status: r.status });
}

const err = (error, status = 400, extra = {}) => ({ status, body: { error, ...extra } });

// 網站顧問與 LINE 機器人共用的核心：回傳 { status, body }；beforeAsk 擋下時回傳 { blocked: beforeAsk 的回傳值 }
export async function advise({ request, env }, { question: q, history }, opts) {
  const question = String(q || "").trim();
  if (!question) return err("請輸入問題");
  if (question.length > MAX_QUESTION) return err(`問題請在 ${MAX_QUESTION} 字以內`);
  const { data, holdings } = await loadData(env, request, opts.dataPath, opts.holdingsPath);
  if (!data) return err("今天的顧問資料還沒產生，請等下一次網站更新", 503);

  let codes = findStocks(question, data.stocks);
  // 問整體持股（集中度、配置）時，帶入權重最大的幾檔持股的資料
  if (!codes.length && holdings && /持股|部位|配置|投資組合|集中|我的股票/.test(question)) {
    codes = holdings.holdings.map((h) => h.code).filter((c) => data.stocks[c]).slice(0, MAX_STOCKS);
  }
  if (!env.GROQ_API_KEY) return err("AI 金鑰還沒設定（GROQ_API_KEY），暫時無法回答", 503, { found: codes });
  if (opts.beforeAsk) {
    const blocked = await opts.beforeAsk();
    if (blocked) return { blocked };
  }
  const priced = new Set(data.price_codes || []);
  const held = Object.fromEntries((holdings?.holdings || []).map((h) => [h.code, h]));

  // 沒在每日計算範圍的股票，記下來，明天起補上風控與回測
  const missing = codes.filter((c) => !priced.has(c));
  if (missing.length && env.DB && !opts.guest) {
    const now = new Date().toISOString();
    await env.DB.batch(missing.map((c) => env.DB.prepare("INSERT OR IGNORE INTO advisor_watch (code, added_at) VALUES (?, ?)").bind(c, now)))
      .catch((exc) => console.error("advisor_watch", exc));
  }

  // 每日資料沒有 PTT（build 主機被擋）時，即時抓
  const full = codes.map((c) => ({ ...data.stocks[c] }));
  if (full.some((s) => !s.ptt)) {
    const titles = await pttTitles();
    if (titles.length) for (const s of full) if (!s.ptt) s.ptt = pttFor(s.code, s.name, titles);
  }
  const stocks = full.map((s) => compactStock(s, held[s.code]));
  const news = await relatedNews(stocks);
  const portfolio = holdings ? {
    as_of: holdings.as_of,
    holdings: holdings.holdings.map((h) => ({ code: h.code, name: h.name, weight_pct: h.weight_pct, pl_pct: h.pl_pct })),
  } : null;
  const context = { generated_at: data.generated_at, stocks };

  let answer;
  try {
    const { raw, tokens } = await askGroq(env, buildMessages({ question, data: context, news, history, portfolio }));
    if (opts.afterAsk) await opts.afterAsk(tokens).catch((exc) => console.error("usage", exc));
    answer = sanitizeAnswer(raw, codes);
    if (answer.quant_camp) answer.quant_camp.points.push(...backtestNotes(stocks));
  } catch (exc) {
    console.error(exc);
    return err("AI 暫時沒有回應，請稍後再試", 502);
  }

  const known = [...collectNumbers(context), ...collectNumbers(portfolio), ...PROMPT_NUMBERS];
  return { status: 200, body: {
    answer,
    unverified: unverifiedNumbers(answer, known),
    stocks: full.map((s) => ({ ...s, held: held[s.code] || null, news: news[s.code] || [] })),
    missing_metrics: missing,
    data_date: data.generated_at,
  } };
}
