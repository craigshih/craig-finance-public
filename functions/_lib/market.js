// 模擬交易的報價與交易成本。
// 報價：證交所（上市）與櫃買中心（上櫃）OpenAPI 的每日收盤價，跟 investment-team/market.py 同一個來源。

// 證交所／櫃買的股名有時帶「*」（官方標示面額不是 10 元），網站上一律拿掉
export const cleanName = (name) => (typeof name === "string" ? name.replace(/\*/g, "").trim() : name);

export const INITIAL_CASH = 1_000_000;
export const FEE_RATE = 0.001425;
export const MAX_SHARES = 10_000_000;

const TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL";
const TPEX = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes";
const CACHE_MS = 30 * 60_000;

export class PublicError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

// 證交稅：股票 0.3%，ETF 0.1%，債券 ETF（代號 00 開頭、B 結尾）免徵
export function taxRate(code) {
  if (/^00\w*B$/.test(code)) return 0;
  if (code.startsWith("00")) return 0.001;
  return 0.003;
}

// 手續費無條件捨去；整股最低 20 元、零股最低 1 元（多數券商的零股優惠）
export function orderCost({ code, side, price, shares }) {
  const amount = Math.round(price * shares);
  const fee = Math.max(shares % 1000 === 0 ? 20 : 1, Math.floor(amount * FEE_RATE));
  const tax = side === "sell" ? Math.floor(amount * taxRate(code)) : 0;
  const total = side === "buy" ? amount + fee : amount - fee - tax;
  return { amount, fee, tax, total };
}

export function validateOrder(body) {
  const code = String(body?.code || "").trim().toUpperCase();
  const side = body?.side;
  const shares = Number(body?.shares);
  if (!/^[0-9A-Z]{4,6}$/.test(code)) throw new PublicError("股票代號格式不正確");
  if (side !== "buy" && side !== "sell") throw new PublicError("買賣別不正確");
  if (!Number.isInteger(shares) || shares < 1 || shares > MAX_SHARES) throw new PublicError("股數要是 1 以上的整數");
  return { code, side, shares };
}

function rocDate(s) {
  if (!/^\d{7}$/.test(s || "")) return null;
  return `${Number(s.slice(0, 3)) + 1911}-${s.slice(3, 5)}-${s.slice(5, 7)}`;
}

export function parseQuotes(twseRows, tpexRows) {
  const out = {};
  for (const r of twseRows || []) {
    const close = Number(String(r.ClosingPrice).replace(/,/g, ""));
    if (close > 0) out[r.Code] = { code: r.Code, name: cleanName(r.Name), price: close, date: rocDate(r.Date), market: "上市" };
  }
  for (const r of tpexRows || []) {
    const close = Number(String(r.Close).replace(/,/g, ""));
    if (close > 0) out[r.SecuritiesCompanyCode] = {
      code: r.SecuritiesCompanyCode, name: cleanName(r.CompanyName), price: close, date: rocDate(r.Date), market: "上櫃",
    };
  }
  return out;
}

let memo = { quotes: null, at: 0 };

async function fetchJson(url) {
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(url, { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`${url} ${res.status}`);
      const j = await res.json();
      if (!Array.isArray(j) || !j.length) throw new Error(`${url} 空的`);
      return j;
    } catch (exc) {
      if (attempt >= 1) throw exc;
      await new Promise((r) => setTimeout(r, 1500)); // 證交所 OpenAPI 偶爾失敗：等一下再試一次
    }
  }
}

// 上市、上櫃兩份清單都要到齊；其中一份讀不到時，用 12 小時內存過的完整清單補（不然搜尋會少掉一整個市場）
const FULL_KEY = new Request("https://sim.cache/quotes-full");
export async function getQuotes() {
  if (memo.quotes && Date.now() - memo.at < CACHE_MS) return memo.quotes;
  const [twse, tpex] = await Promise.allSettled([fetchJson(TWSE), fetchJson(TPEX)]);
  const ok = twse.status === "fulfilled" && tpex.status === "fulfilled";
  let quotes = parseQuotes(twse.status === "fulfilled" ? twse.value : [], tpex.status === "fulfilled" ? tpex.value : []);
  const cache = typeof caches !== "undefined" ? caches.default : null;
  if (ok && cache) {
    await cache.put(FULL_KEY, new Response(JSON.stringify(quotes), { headers: { "Cache-Control": "max-age=43200" } })).catch(() => {});
  } else if (!ok) {
    const old = memo.quotes || (cache && (await cache.match(FULL_KEY).then((r) => r && r.json()).catch(() => null)));
    if (old) quotes = { ...old, ...quotes };
  }
  if (!Object.keys(quotes).length) throw new PublicError("報價暫時無法取得，請稍後再試", 503);
  memo = { quotes, at: ok ? Date.now() : Date.now() - CACHE_MS + 60_000 }; // 不完整時一分鐘後再試
  return quotes;
}

// 持股估值：用最新收盤價，沒有報價的（例如已下市）以成本計
export function valuate(holdings, quotes) {
  let value = 0;
  const rows = holdings.map((h) => {
    const q = quotes[h.code];
    const price = q ? q.price : null;
    const mv = price != null ? Math.round(price * h.shares) : h.cost;
    value += mv;
    return {
      code: h.code, name: cleanName(h.name || q?.name || h.code), shares: h.shares, cost: h.cost,
      avg_cost: h.shares ? h.cost / h.shares : 0, price, value: mv, pl: mv - h.cost,
      pl_pct: h.cost ? (mv - h.cost) / h.cost : 0,
    };
  });
  rows.sort((a, b) => b.value - a.value);
  return { rows, value };
}

// ---------- 搜尋、盤中即時價 ----------

// 代號或中文名稱都可以搜：代號完全符合 > 代號開頭 > 名稱開頭 > 名稱包含
export function searchStocks(quotes, q, limit = 8) {
  const s = String(q || "").trim().toUpperCase().replace(/\s+/g, "");
  if (!s) return [];
  const scored = [];
  for (const x of Object.values(quotes)) {
    const name = x.name.replace(/\s+/g, "").toUpperCase();
    let score = null;
    if (x.code === s) score = 0;
    else if (name === s) score = 1;
    else if (x.code.startsWith(s)) score = 2;
    else if (name.startsWith(s)) score = 3;
    else if (name.includes(s)) score = 4;
    if (score != null) scored.push([score, x.code.length, x.code, x]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2].localeCompare(b[2]));
  return scored.slice(0, limit).map(([, , , x]) => ({ code: x.code, name: x.name, market: x.market, price: x.price }));
}

// 台股盤中：週一到週五 09:00～13:30（台北時間）；不處理國定假日（休市時 MIS 會回昨收，不影響）
export function marketOpen(now = new Date()) {
  const t = new Date(now.getTime() + 8 * 3600_000);
  const day = t.getUTCDay();
  const mins = t.getUTCHours() * 60 + t.getUTCMinutes();
  return day >= 1 && day <= 5 && mins >= 9 * 60 && mins <= 13 * 60 + 30;
}

// 限價委託的有效期限：當天（或下一個平日）台北 13:30
export function nextClose(now = new Date()) {
  const t = new Date(now.getTime() + 8 * 3600_000);
  const close = (d) => Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 13, 30) - 8 * 3600_000;
  let d = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate()));
  while (d.getUTCDay() === 0 || d.getUTCDay() === 6 || close(d) < now.getTime()) d = new Date(d.getTime() + 86400_000);
  return new Date(close(d)).toISOString();
}
