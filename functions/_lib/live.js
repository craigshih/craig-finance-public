// 盤中即時報價：台股個股與大盤用證交所基本市況報導（MIS），國際指數用 Yahoo Finance spark。
// 每次重新整理網頁，前端都會來拿一次，伺服器端 60 秒內共用同一份結果，不會打爆來源。

export const INDEX_SYMBOLS = {
  "^TWII": "台股加權", "^TWOII": "櫃買指數", "TSM": "台積電 ADR", "^SOX": "費城半導體", "^GSPC": "S&P 500",
  "^IXIC": "那斯達克", "^DJI": "道瓊", "^RUT": "羅素 2000", "^N225": "日經 225", "^KS11": "韓國綜合", "^VIX": "VIX", "CL=F": "WTI 原油",
  "DX-Y.NYB": "美元指數", "TWD=X": "美元兌台幣",
};
export const MAX_CODES = 80;

const num = (s) => {
  const v = Number(String(s ?? "").replace(/,/g, ""));
  return Number.isFinite(v) && v > 0 ? v : null;
};
const firstBook = (s) => num(String(s || "").split("_")[0]);

// MIS 盤中如果這一刻沒有成交，z 會是 "-"：依序改用最後成交 pz、買賣價中間、昨收
export function parseMis(json) {
  const out = {};
  for (const m of json?.msgArray || []) {
    const prev = num(m.y);
    const bid = firstBook(m.b), ask = firstBook(m.a);
    const price = num(m.z) ?? num(m.pz) ?? (bid && ask ? (bid + ask) / 2 : null) ?? prev;
    if (!price || !prev) continue;
    const code = m.c === "t00" ? "^TWII" : m.c === "o00" ? "^TWOII" : m.c;
    out[code] = {
      price, prev, chg: +(price - prev).toFixed(4), pct: +((price / prev - 1) * 100).toFixed(2),
      // 用資料日 d＋時間 t（台北時間）組出成交時間；tlong 實測會差一小時，只當備用
      time: /^\d{8}$/.test(m.d || "") && /^\d\d:\d\d:\d\d$/.test(m.t || "")
        ? new Date(`${m.d.slice(0, 4)}-${m.d.slice(4, 6)}-${m.d.slice(6, 8)}T${m.t}+08:00`).toISOString()
        : m.tlong ? new Date(Number(m.tlong)).toISOString() : null, name: m.n ? m.n.replace(/\*/g, "").trim() : null,
      // 模擬交易要用的盤面：開高低、漲跌停、最佳一檔買賣價、成交量（張）、資料日
      open: num(m.o), high: num(m.h), low: num(m.l), upper: num(m.u), lower: num(m.w), ask, bid,
      volume: num(m.v), day: /^\d{8}$/.test(m.d || "") ? `${m.d.slice(0, 4)}-${m.d.slice(4, 6)}-${m.d.slice(6, 8)}` : null,
      market: m.ex === "otc" ? "上櫃" : m.ex === "tse" ? "上市" : null,
    };
  }
  return out;
}

export function parseSpark(json) {
  const out = {};
  for (const r of json?.spark?.result || []) {
    const meta = r.response?.[0]?.meta;
    const price = num(meta?.regularMarketPrice), prev = num(meta?.chartPreviousClose ?? meta?.previousClose);
    if (!price || !prev) continue;
    out[r.symbol] = {
      price, prev, chg: +(price - prev).toFixed(4), pct: +((price / prev - 1) * 100).toFixed(2),
      time: meta.regularMarketTime ? new Date(meta.regularMarketTime * 1000).toISOString() : null,
    };
  }
  return out;
}

export function validCodes(raw) {
  return [...new Set(String(raw || "").split(",").map((c) => c.trim().toUpperCase()).filter((c) => /^[0-9]{4,6}[A-Z]?$/.test(c)))].slice(0, MAX_CODES);
}

// 不知道上市還上櫃，兩個都問；MIS 只會回傳存在的那一個
export function misChannels(codes) {
  return codes.flatMap((c) => [`tse_${c}.tw`, `otc_${c}.tw`]);
}

export function validUs(raw) {
  return [...new Set(String(raw || "").split(",").map((c) => c.trim().toUpperCase()).filter((c) => /^[A-Z][A-Z.\-]{0,6}$/.test(c)))].slice(0, MAX_CODES);
}
