// 模擬交易的「證券商規則」：升降單位、漲跌停、交易時段、整股／零股、委託撮合。
// 都是純函式，方便測試；規則依證交所現行制度（普通交易 09:00～13:30、漲跌幅 10%、ROD 當日有效）。

const TPE = 8 * 3600_000;
const DAY = 86400_000;

export const isEtf = (code) => String(code).startsWith("00");

// 升降單位（tick）：股票依價位六級；ETF 未滿 50 元 0.01、50 元以上 0.05
export function tickSize(price, code) {
  if (isEtf(code)) return price < 50 ? 0.01 : 0.05;
  if (price < 10) return 0.01;
  if (price < 50) return 0.05;
  if (price < 100) return 0.1;
  if (price < 500) return 0.5;
  if (price < 1000) return 1;
  return 5;
}

const r2 = (x) => Math.round(x * 100) / 100;
export function onTick(price, code) {
  const t = tickSize(price, code);
  return Math.abs(price / t - Math.round(price / t)) < 1e-6;
}
const floorTick = (x, code) => { const t = tickSize(x, code); return r2(Math.floor(x / t + 1e-9) * t); };
const ceilTick = (x, code) => { const t = tickSize(x, code); return r2(Math.ceil(x / t - 1e-9) * t); };

// 漲跌停：參考價 ±10%，漲停往下、跌停往上取到合法價位
export function limitBand(ref, code) {
  return { upper: floorTick(ref * 1.1, code), lower: ceilTick(ref * 0.9, code) };
}

// 整股（1,000 股的倍數）和零股（1～999 股）在交易所是不同的交易，券商一張委託只能是其中一種
export function shareRule(shares) {
  if (shares >= 1000 && shares % 1000 !== 0) return "整股（1,000 股的倍數）和零股（1～999 股）要分開下單";
  return null;
}

export const taipeiDay = (ms) => new Date(ms + TPE).toISOString().slice(0, 10);
const isWeekday = (day) => { const d = new Date(`${day}T00:00:00Z`).getUTCDay(); return d >= 1 && d <= 5; };
export const closeAt = (day) => new Date(Date.parse(`${day}T13:30:00+08:00`)).toISOString();

export function nextWeekday(day) {
  let t = Date.parse(`${day}T00:00:00Z`) + DAY;
  while (!isWeekday(new Date(t).toISOString().slice(0, 10))) t += DAY;
  return new Date(t).toISOString().slice(0, 10);
}

// 現在的交易時段。quoteDay 是即時報價的資料日：平日 9 點多了報價還停在前一天，代表今天休市（國定假日）
export function session(now = Date.now(), quoteDay = null) {
  const day = taipeiDay(now);
  const mins = Math.floor(((now + TPE) % DAY) / 60_000);
  const weekday = isWeekday(day);
  const holiday = weekday && mins >= 9 * 60 + 5 && quoteDay && quoteDay < day;
  const open = weekday && !holiday && mins >= 9 * 60 && mins < 13 * 60 + 30;
  // 下一個可以成交的交易日：盤中是今天；開盤前是今天；收盤後、週末、假日是下一個平日
  const next = open || (weekday && !holiday && mins < 9 * 60) ? day : nextWeekday(day);
  let label;
  if (open) label = "盤中";
  else if (!weekday || holiday) label = "休市";
  else if (mins < 9 * 60) label = "盤前";
  else label = "已收盤";
  return { open, label, day, next };
}

// 現在送出的委託會在哪個交易日處理（ROD 當日有效；非交易時間送出的是預約單）
export function orderSession(now = Date.now(), quoteDay = null) {
  const s = session(now, quoteDay);
  return { day: s.next, expires: closeAt(s.next), reserved: !s.open };
}

// 盤中立即成交價：買進吃最佳賣價、賣出吃最佳買價（跟真的下市價單一樣）；
// 漲停鎖住沒有賣單就買不到，跌停鎖住沒有買單就賣不掉
export function marketFill(side, q) {
  if (side === "buy") {
    if (q.ask) return q.ask;
    return q.upper && q.price >= q.upper ? null : q.price;
  }
  if (q.bid) return q.bid;
  return q.lower && q.price <= q.lower ? null : q.price;
}

// 掛著的委託要不要成交。q 是委託交易日當天的報價（含開高低）；
// 盤中下的限價單用下單當下記住的最高、最低價（seen_high / seen_low），只有之後真的碰到委託價才算成交
export function decideFill(o, q) {
  if (!q || q.day !== o.session) return null;
  const preOpen = o.seen_high == null; // 預約單：開盤前就在排隊，先看開盤價
  if (o.kind === "market") return q.open ? { price: q.open, note: "開盤價成交" } : null;
  const L = o.limit_price;
  if (o.side === "buy") {
    if (preOpen && q.open && q.open <= L) return { price: q.open, note: "開盤價成交" };
    if (q.ask && q.ask <= L) return { price: q.ask, note: "成交" };   // 現在的賣價已經到價
    const low = q.low ?? q.price;
    if (low <= L && (preOpen || low < o.seen_low)) return { price: L, note: "到價成交" };
  } else {
    if (preOpen && q.open && q.open >= L) return { price: q.open, note: "開盤價成交" };
    if (q.bid && q.bid >= L) return { price: q.bid, note: "成交" };
    const high = q.high ?? q.price;
    if (high >= L && (preOpen || high > o.seen_high)) return { price: L, note: "到價成交" };
  }
  return null;
}
