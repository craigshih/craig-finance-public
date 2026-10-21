// GET /api/live?tw=2330,6274&us=NVDA,AAPL&idx=1 → { tw: {代號: 報價}, us: {美股: 報價}, idx: {指數: 報價}, updated }
// 全站共用：頂部跑馬燈、市場頁指數、投資頁持股市值都靠它在每次開啟時更新到最新。

import { INDEX_SYMBOLS, SCALE, misChannels, parseMis, parseSpark, validCodes, validUs } from "../_lib/live.js";

const UA = "Mozilla/5.0 (compatible; craig-finance-hub/1.0)";
const TTL = 60;

export async function cached(key, fetcher) {
  const cache = caches.default;
  const req = new Request(`https://live.cache/${key}`);
  const hit = await cache.match(req);
  if (hit) return hit.json();
  const data = await fetcher();
  if (data && Object.keys(data).length) {
    await cache.put(req, new Response(JSON.stringify(data), { headers: { "Cache-Control": `max-age=${TTL}` } }));
  }
  return data;
}

export async function mis(channels) {
  const out = {};
  for (let i = 0; i < channels.length; i += 60) {
    const url = `https://mis.twse.com.tw/stock/api/getStockInfo.jsp?json=1&delay=0&ex_ch=${channels.slice(i, i + 60).join("|")}`;
    try {
      const res = await fetch(url, { headers: { "User-Agent": UA, Referer: "https://mis.twse.com.tw/stock/index.jsp" } });
      if (res.ok) Object.assign(out, parseMis(await res.json()));
    } catch (exc) {
      console.error("mis", exc);
    }
  }
  return out;
}

async function spark(symbols) {
  const out = {};
  for (let i = 0; i < symbols.length; i += 20) {
    const part = symbols.slice(i, i + 20).map((s) => s.replace(".", "-"));
    try {
      const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/spark?range=1d&interval=1d&symbols=${part.map(encodeURIComponent).join(",")}`, { headers: { "User-Agent": UA } });
      if (res.ok) for (const [k, v] of Object.entries(parseSpark(await res.json()))) out[k.replace("-", ".")] = v;
    } catch (exc) {
      console.error("spark", exc);
    }
  }
  return out;
}

export async function indices() {
  const intl = Object.keys(INDEX_SYMBOLS).filter((s) => s !== "^TWII" && s !== "^TWOII");
  const [tw, spark] = await Promise.all([
    mis(["tse_t00.tw", "otc_o00.tw"]),
    fetch(`https://query1.finance.yahoo.com/v7/finance/spark?range=1d&interval=1d&symbols=${intl.map(encodeURIComponent).join(",")}`,
      { headers: { "User-Agent": UA } }).then((r) => (r.ok ? r.json() : null)).then(parseSpark).catch(() => ({})),
  ]);
  const out = {};
  for (const [sym, name] of Object.entries(INDEX_SYMBOLS)) {
    const q = tw[sym] || spark[sym];
    const k = SCALE[sym] || 1;
    if (q) out[sym] = { ...q, price: q.price * k, prev: q.prev * k, chg: +(q.chg * k).toFixed(4), name };
  }
  return out;
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  const codes = validCodes(url.searchParams.get("tw"));
  const us = validUs(url.searchParams.get("us"));
  const [tw, idx, usq] = await Promise.all([
    codes.length ? cached(`tw/${codes.sort().join(",")}`, () => mis(misChannels(codes))) : {},
    url.searchParams.get("idx") ? cached("idx", indices) : null,
    us.length ? cached(`us/${us.sort().join(",")}`, () => spark(us)) : {},
  ]);
  return Response.json({ updated: new Date().toISOString(), tw, idx, us: usq }, { headers: { "Cache-Control": "no-store" } });
}
