// LINE Messaging API 的小工具：驗證 webhook 簽章、回覆訊息。
// 金鑰：LINE_CHANNEL_SECRET（驗簽章）、LINE_CHANNEL_ACCESS_TOKEN（呼叫 API），都存在 Cloudflare 的 secrets。

const enc = new TextEncoder();

// X-Line-Signature＝HMAC-SHA256(channel secret, 原始 body) 的 base64
export async function validSignature(secret, body, signature) {
  if (!secret || !signature) return false;
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(body)));
  const b64 = btoa(String.fromCharCode(...sig));
  if (b64.length !== signature.length) return false;
  let diff = 0;
  for (let i = 0; i < b64.length; i++) diff |= b64.charCodeAt(i) ^ signature.charCodeAt(i);
  return diff === 0;
}

// 回覆（reply）不算推播額度；一次最多 5 則。有 quoteToken 時第一則會引用對方那句話（群組裡看得出在回誰）
export async function reply(token, replyToken, texts, { quoteToken } = {}) {
  const messages = texts.filter(Boolean).slice(0, 5).map((text, i) => ({
    type: "text", text: text.slice(0, 5000), ...(i === 0 && quoteToken ? { quoteToken } : {}),
  }));
  if (!token || !replyToken || !messages.length) return false;
  const res = await fetch("https://api.line.me/v2/bot/message/reply", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ replyToken, messages }),
  });
  if (!res.ok) console.error("LINE reply", res.status, await res.text());
  return res.ok;
}

// 一對一聊天時顯示「輸入中」動畫，等 AI 回答比較不會以為當機（群組不支援）
export async function startLoading(token, userId, seconds = 30) {
  if (!token || !userId) return;
  await fetch("https://api.line.me/v2/bot/chat/loading/start", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ chatId: userId, loadingSeconds: seconds }),
  }).catch(() => {});
}

// ---------- 指令判斷（整句符合才觸發，群組聊天提到這些字不會誤觸發） ----------

const END = "[!！?？。.\\s]*$";
export const ASK_WORDS = new RegExp(`^(今日一檔|每日一檔|一檔|今天一檔)${END}`);
export const HELP_WORDS = new RegExp(`^(說明|使用說明|幫助|指令|功能|help)${END}`, "i");
export const MARKET_WORDS = new RegExp(`^(大盤|今日大盤|台股大盤|指數|盤勢)${END}`);
export const FORTUNE_WORDS = new RegExp(`^(抽籤|求籤|抽一支|今日股運|股運|今日運勢|運勢)${END}`);
export const MAX_QUOTES = 5;

export const HELP = [
  "我是韭菜仔 🥬 被割過無數次的老韭菜，Craig 財經站的吉祥物。會這些：",
  "📈 查股價：打代號或名稱，例如「2330」「台積電」「2330 2317」",
  "🌏 看大盤：打「大盤」",
  "📰 今日一檔：打「今日一檔」",
  "🎋 今日股運：打「抽籤」，每人每天一支",
  "💬 找我聊天、嗆我：句子裡有「韭菜仔」或 @我 就好（私訊不用叫）",
  "🔍 認真問股票：例如「韭菜仔 聯電跟台積電哪個風險高？」我會翻資料認真回（每人每天 5 題）",
  "※ 我講的聽聽就好，不構成投資建議。",
].join("\n");

// 把 @機器人 從訊息裡拿掉；mentioned＝這句話有沒有 @ 到機器人自己
export function stripMention(message) {
  let text = String(message?.text || "");
  const self = (message?.mention?.mentionees || []).filter((m) => m.isSelf).sort((a, b) => b.index - a.index);
  for (const m of self) text = text.slice(0, m.index) + text.slice(m.index + m.length);
  return { text: text.trim(), mentioned: self.length > 0 };
}

const shortName = (name) => String(name || "").replace(/-KY$|\*$/g, "").trim();
const nameMemo = new WeakMap();
function nameIndex(stocks, aliases) {
  if (nameMemo.has(stocks)) return nameMemo.get(stocks);
  const idx = new Map(Object.entries(aliases));
  for (const [code, s] of Object.entries(stocks)) if (shortName(s.name)) idx.set(shortName(s.name), code);
  nameMemo.set(stocks, idx);
  return idx;
}

// 「2330」「台積電」「查 2330 2317」「鴻海股價？」→ 代號清單；有任何一個字認不得就不是查價（回傳 null）
export function quoteCodes(text, stocks = {}, aliases = {}) {
  const t = String(text || "").trim().replace(/^查(詢)?\s*/, "").replace(/\s*(的)?(股價|報價|現在多少|多少錢|多少)?[!！?？。.\s]*$/, "");
  if (!t || t.length > 40) return null;
  const idx = nameIndex(stocks, aliases);
  const codes = [];
  for (const tok of t.split(/[\s,，、]+/).filter(Boolean)) {
    const code = /^[0-9]{4,6}[A-Za-z]?$/.test(tok) ? tok.toUpperCase() : idx.get(shortName(tok));
    if (!code) return null;
    if (!codes.includes(code)) codes.push(code);
  }
  return codes.length && codes.length <= MAX_QUOTES ? codes : null;
}

// ---------- 回覆文字 ----------

const fmt = (n, d = 2) => Number(n).toLocaleString("en-US", { maximumFractionDigits: d });
const taipei = (iso) => new Date(new Date(iso).getTime() + 8 * 3600_000);
// 顯示時間一律取到 5 分鐘、不顯示秒
export function clock(iso, now = Date.now()) {
  if (!iso || Number.isNaN(new Date(iso).getTime())) return "";
  const t = taipei(iso), today = taipei(now).toISOString().slice(0, 10);
  const hm = `${String(t.getUTCHours()).padStart(2, "0")}:${String(Math.floor(t.getUTCMinutes() / 5) * 5).padStart(2, "0")}`;
  return t.toISOString().slice(0, 10) === today ? `今天 ${hm}` : `${t.getUTCMonth() + 1}/${t.getUTCDate()} ${hm}`;
}

function move(q) {
  if (!q.chg) return "平盤";
  const arrow = q.chg > 0 ? "▲" : "▼";
  return `${arrow}${fmt(Math.abs(q.chg))}（${q.pct > 0 ? "+" : ""}${q.pct.toFixed(2)}%）`;
}

export function formatQuote(code, q, stocks = {}, now = Date.now()) {
  const name = q.name || shortName(stocks[code]?.name) || code;
  const limit = q.upper && q.price >= q.upper ? " 漲停" : q.lower && q.price <= q.lower ? " 跌停" : "";
  const lines = [`📈 ${name} ${code}${q.market ? `（${q.market}）` : ""}`, `${fmt(q.price)} 元　${move(q)}${limit}`];
  const ohl = [["開", q.open], ["高", q.high], ["低", q.low]].filter(([, v]) => v).map(([k, v]) => `${k} ${fmt(v)}`);
  if (q.volume) ohl.push(`量 ${fmt(q.volume, 0)} 張`);
  if (ohl.length) lines.push(ohl.join("　"));
  const at = clock(q.time, now);
  if (at) lines.push(`🕒 ${at}`);
  return lines.join("\n");
}

export const MARKET_ORDER = ["^TWII", "^TWOII", "TSM", "^SOX", "^IXIC", "^GSPC", "^DJI", "^VIX", "TWD=X"];

export function formatIndices(idx, now = Date.now()) {
  const rows = MARKET_ORDER.filter((s) => idx?.[s]).map((s) => {
    const q = idx[s];
    return `${q.name}　${fmt(q.price)}　${q.chg ? `${q.chg > 0 ? "▲" : "▼"}${Math.abs(q.pct).toFixed(2)}%` : "平盤"}`;
  });
  if (!rows.length) return "現在抓不到指數報價，等一下再試試 🙏";
  const latest = Object.values(idx).map((q) => q.time).filter(Boolean).sort().pop();
  return ["🌏 大盤與國際指數", ...rows, latest ? `🕒 ${clock(latest, now)}` : ""].filter(Boolean).join("\n");
}

export const AI_FOOTER = "※ AI 依公開資料整理，僅供學習研究，不構成投資建議。";

// 網站顧問的回答（兩派辯論）濃縮成 LINE 好讀的長度
export function formatAnswer(body, opener = "") {
  const a = body?.answer || {};
  const names = Object.fromEntries((body?.stocks || []).map((s) => [s.code, shortName(s.name)]));
  const parts = [`${opener ? `${opener}\n` : ""}💬 ${a.headline || "（AI 沒有給出結論）"}`];
  if (a.mode === "coach" && a.coach) parts.push(a.coach);
  else if (a.synthesis?.conclusion) parts.push(a.synthesis.conclusion);
  else if (a.coach) parts.push(a.coach);
  const st = (a.stocks || []).filter((s) => s.summary).map((s) => `・${names[s.code] || s.code}（${s.code}）${s.stance}：${s.summary}`);
  if (a.mode !== "coach" && st.length) parts.push(st.join("\n"));
  if (a.synthesis?.conditions?.length) parts.push(`🔄 什麼情況會改變看法\n${a.synthesis.conditions.map((c) => `・${c}`).join("\n")}`);
  if (body?.unverified?.length) parts.push(`⚠️ 回答裡有 ${body.unverified.length} 個數字在資料裡找不到出處，請自行查證`);
  if (a.follow_ups?.length) parts.push(`👉 可以再問：${a.follow_ups.slice(0, 2).join("／")}`);
  const date = String(body?.data_date || "").slice(0, 10);
  parts.push(date ? `${AI_FOOTER}（資料日 ${date}）` : AI_FOOTER);
  return parts.join("\n\n").slice(0, 5000);
}
