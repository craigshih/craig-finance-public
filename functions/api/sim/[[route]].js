// 模擬交易 API。身分來自 Cloudflare Access 登入的 email；所有價格都在伺服器端查，不信任瀏覽器送來的價格。
//
//   GET  /api/sim/me              我的帳戶、持股、近期成交、委託、資產走勢（順便撮合到價的限價單）
//   GET  /api/sim/search?q=       用代號或名稱找股票（例如 2330、台積、元大）
//   GET  /api/sim/quote?code=     查報價（盤中用證交所即時價，收盤後用收盤價）
//   GET  /api/sim/chart?code=     半年日 K、5/20/60 日均線、成交量、四指標體檢
//   POST /api/sim/order           下單 {code, side: buy|sell, shares, type: market|limit, limit_price}
//   POST /api/sim/cancel          取消限價委託 {id}
//   GET  /api/sim/watch           自選股（含報價與四指標體檢）
//   POST /api/sim/watch           加入／移除自選 {code, on: true|false}
//   GET  /api/sim/leaderboard     排行榜（只顯示暱稱）
//   POST /api/sim/nickname        改暱稱 {nickname}
//   POST /api/sim/reset           重新開始（清空持股、委託、走勢，資金回到初始值；自選股保留）

import { accessEmail } from "../../_lib/auth.js";
import { misChannels, parseMis } from "../../_lib/live.js";
import {
  INITIAL_CASH, PublicError, getQuotes, marketOpen, nextClose, orderCost, searchStocks, validateOrder, valuate, cleanName } from "../../_lib/market.js";
import { computeSignals, maSeries, parseYahooChart } from "../../_lib/signals.js";
import {
  closeAt, decideFill, limitBand, marketFill, nextWeekday, onTick, orderSession, session, shareRule, taipeiDay, tickSize,
} from "../../_lib/broker.js";

const UA = "Mozilla/5.0 (compatible; craig-finance-hub/1.0)";
const json = (data, status = 200) =>
  new Response(JSON.stringify(data, (k, v) => (k === "name" ? cleanName(v) : v)), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });

const defaultNickname = (email) => `${email.split("@")[0].slice(0, 2)}***`;
const taipeiDate = (d = new Date()) => new Date(d.getTime() + 8 * 3600_000).toISOString().slice(0, 10);

async function ensurePlayer(db, email) {
  await db
    .prepare("INSERT OR IGNORE INTO players (email, nickname, cash, created_at, resets) VALUES (?, ?, ?, ?, 0)")
    .bind(email, defaultNickname(email), INITIAL_CASH, new Date().toISOString())
    .run();
  return db.prepare("SELECT * FROM players WHERE email = ?").bind(email).first();
}

// ---------- 報價 ----------
// 每次重新整理都用證交所「基本市況報導」（MIS）的即時盤面：盤中是當下成交價與最佳買賣價，收盤後是今天的收盤價。
// 伺服器端最多共用 10 秒；證交所／櫃買 OpenAPI 的每日收盤檔（更新較慢）只拿來做股票清單與搜尋。

async function cached(key, ttl, fetcher) {
  const req = new Request(`https://sim.cache/${key}`);
  const hit = await caches.default.match(req);
  if (hit) return hit.json();
  const data = await fetcher();
  if (data) await caches.default.put(req, new Response(JSON.stringify(data), { headers: { "Cache-Control": `max-age=${ttl}` } }));
  return data;
}

async function misQuotes(codes) {
  const list = [...new Set(codes)].sort();
  const out = {};
  for (let i = 0; i < list.length; i += 40) {
    const chunk = list.slice(i, i + 40);
    Object.assign(out, await cached(`mis/${chunk.join(",")}`, 10, async () => {
      try {
        const res = await fetch(`https://mis.twse.com.tw/stock/api/getStockInfo.jsp?json=1&delay=0&ex_ch=${misChannels(chunk).join("|")}`,
          { headers: { "User-Agent": UA, Referer: "https://mis.twse.com.tw/stock/index.jsp" } });
        return res.ok ? parseMis(await res.json()) : {};
      } catch {
        return {};
      }
    }) || {});
  }
  return out;
}

// 合併：名稱、市場別用股票清單；價格一律用即時盤面，讀不到才退回每日收盤檔
async function priceMap(codes, quotes) {
  const live = await misQuotes(codes);
  const out = {};
  for (const c of codes) {
    const base = quotes[c], l = live[c];
    if (!base && !l) continue;
    const name = base?.name || l?.name || c, market = base?.market || l?.market || "上市";
    if (l) {
      const s = session(Date.now(), l.day);
      out[c] = { ...l, code: c, name, market, date: l.day, source: s.open ? "即時" : "收盤", session: s.label, tick: tickSize(l.price, c) };
    } else {
      // 即時盤面讀不到：退回每日收盤檔。這份資料常停在前一天，不能拿來判斷今天有沒有開盤（day 留空），也不能拿來成交
      out[c] = { ...base, source: "收盤", session: session().label, time: null, day: null, stale: true, tick: tickSize(base.price, c) };
    }
  }
  return out;
}

async function quoteOf(code, quotes) {
  if (!/^[0-9A-Z]{4,6}$/.test(code)) throw new PublicError("股票代號格式不正確");
  const q = (await priceMap([code], quotes))[code];
  if (!q) throw new PublicError(`找不到 ${code} 的報價（目前支援上市、上櫃股票與 ETF）`, 404);
  // 收盤後下的單是明天的預約單：漲跌停改用今天收盤價推算的明日區間
  const s = session(Date.now(), q.day);
  const band = !s.open && q.price ? limitBand(q.price, code) : { upper: q.upper, lower: q.lower };
  return { ...q, order_day: orderSession(Date.now(), q.day).day, order_upper: band.upper, order_lower: band.lower };
}

async function chart(code, quotes) {
  const q = quotes[code];
  if (!q) throw new PublicError(`找不到 ${code}`, 404);
  const sym = `${code}.${q.market === "上櫃" ? "TWO" : "TW"}`;
  const [rows, live] = await Promise.all([
    cached(`chart/${sym}`, 120, async () => {
      const res = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${sym}?range=6mo&interval=1d`, { headers: { "User-Agent": UA } });
      if (!res.ok) return null;
      const r = parseYahooChart(await res.json());
      return r.length ? r : null;
    }),
    misQuotes([code]),
  ]);
  if (!rows) throw new PublicError("走勢資料暫時讀不到", 503);
  // Yahoo 的日 K 常慢一點：用即時盤面補上（或覆蓋）今天這根
  const l = live[code];
  if (l?.day && l.open && l.high && l.low) {
    const bar = { date: l.day, open: l.open, high: l.high, low: l.low, close: l.price, volume: (l.volume || 0) * 1000 };
    if (rows[rows.length - 1].date === l.day) rows[rows.length - 1] = bar;
    else if (rows[rows.length - 1].date < l.day) rows.push(bar);
  }
  const ma5 = maSeries(rows, 5), ma20 = maSeries(rows, 20), ma60 = maSeries(rows, 60);
  const start = Math.max(0, rows.length - 120);
  return {
    code, name: q.name, market: q.market,
    rows: rows.slice(start).map((r, i) => ({ ...r, ma5: ma5[start + i], ma20: ma20[start + i], ma60: ma60[start + i] })),
    signals: computeSignals(rows),
  };
}

// ---------- 交易 ----------

async function execute(db, email, { code, side, shares }, q, price) {
  const cost = orderCost({ code, side, price, shares });
  const now = new Date().toISOString();
  const when = q.time ? new Date(Date.parse(q.time) + 8 * 3600_000).toISOString().slice(11, 19) : "";
  const tradeStmt = db
    .prepare("INSERT INTO trades (email, ts, code, name, side, shares, price, amount, fee, tax, price_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
    .bind(email, now, code, q.name, side, shares, price, cost.amount, cost.fee, cost.tax, `${q.day || q.date || taipeiDate()} ${when}`.trim());

  if (side === "buy") {
    // 條件式扣款：同時送出兩張單也不會把現金扣成負數
    const r = await db.prepare("UPDATE players SET cash = cash - ? WHERE email = ? AND cash >= ?").bind(cost.total, email, cost.total).run();
    if (!r.meta.changes) throw new PublicError("現金不足");
    await db.batch([
      db.prepare(`INSERT INTO holdings (email, code, name, shares, cost) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT (email, code) DO UPDATE SET shares = shares + excluded.shares, cost = cost + excluded.cost, name = excluded.name`)
        .bind(email, code, q.name, shares, cost.total),
      tradeStmt,
    ]);
    return { ...cost, realized: null };
  }
  const h = await db.prepare("SELECT shares, cost FROM holdings WHERE email = ? AND code = ?").bind(email, code).first();
  if (!h || h.shares < shares) throw new PublicError(`持股不足（目前 ${h ? h.shares : 0} 股）`);
  const costOut = Math.round((h.cost * shares) / h.shares); // 依比例減少持有成本
  const r = await db.prepare("UPDATE holdings SET shares = shares - ?, cost = cost - ? WHERE email = ? AND code = ? AND shares = ?")
    .bind(shares, costOut, email, code, h.shares).run();
  if (!r.meta.changes) throw new PublicError("持股剛剛有變動，請再試一次", 409);
  const realized = cost.total - costOut;
  await db.batch([
    db.prepare("UPDATE players SET cash = cash + ? WHERE email = ?").bind(cost.total, email),
    db.prepare("DELETE FROM holdings WHERE email = ? AND code = ? AND shares = 0").bind(email, code),
    db.prepare("INSERT INTO sim_realized (email, ts, code, realized) VALUES (?, ?, ?, ?)").bind(email, now, code, realized),
    tradeStmt,
  ]);
  return { ...cost, realized };
}

const mmdd = (day) => `${Number(day.slice(5, 7))}/${Number(day.slice(8, 10))}`;

async function queueOrder(db, email, order, q, kind, limit, ses, live) {
  const open = await db.prepare("SELECT COUNT(*) AS n FROM sim_orders WHERE email = ? AND status = 'open'").bind(email).first();
  if (open.n >= 20) throw new PublicError("同時最多 20 筆委託");
  await db.prepare(`INSERT INTO sim_orders (email, ts, code, name, side, shares, limit_price, status, expires, kind, session, seen_high, seen_low)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)`)
    .bind(email, new Date().toISOString(), order.code, q.name, order.side, order.shares, limit, ses.expires, kind, ses.day,
      live ? q.high ?? q.price : null, live ? q.low ?? q.price : null).run();
  return { ok: true, filled: false, ...order, name: q.name, kind, limit_price: limit, session: ses.day, reserved: ses.reserved,
    message: ses.reserved ? `預約單已排入 ${mmdd(ses.day)} 開盤${kind === "market" ? "，以開盤價成交" : ""}` : "委託已掛出，到價就成交（當日有效）" };
}

async function placeOrder(db, email, body) {
  const order = validateOrder(body);
  const lotErr = shareRule(order.shares);
  if (lotErr) throw new PublicError(lotErr);
  const type = body?.type === "limit" ? "limit" : "market";
  await ensurePlayer(db, email);
  const q = await quoteOf(order.code, await getQuotes());
  const ses = orderSession(Date.now(), q.day);
  const live = !ses.reserved; // 盤中
  if (q.stale && live) throw new PublicError("證交所即時報價暫時讀不到，為了不用舊價格成交，請稍後再試", 503);
  const player = await db.prepare("SELECT cash FROM players WHERE email = ?").bind(email).first();
  if (order.side === "sell") {
    const h = await db.prepare("SELECT shares FROM holdings WHERE email = ? AND code = ?").bind(email, order.code).first();
    if (!h || h.shares < order.shares) throw new PublicError(`持股不足（目前 ${h ? h.shares : 0} 股）`);
  }

  if (type === "limit") {
    const limit = Math.round(Number(body?.limit_price) * 100) / 100;
    if (!(limit > 0)) throw new PublicError("請輸入委託價");
    const upper = q.order_upper, lower = q.order_lower;
    if (upper && lower && (limit > upper || limit < lower)) throw new PublicError(`委託價要在跌停 ${lower} 到漲停 ${upper} 之間`);
    if (!onTick(limit, order.code)) throw new PublicError(`委託價不符合升降單位（這個價位每檔 ${tickSize(limit, order.code)} 元）`);
    if (order.side === "buy" && orderCost({ code: order.code, side: "buy", price: limit, shares: order.shares }).total > player.cash) {
      throw new PublicError("現金不足（以委託價計算）");
    }
    if (live) {
      // 盤中：委託價已經碰到對手價就立即成交，成交在對手價（較好的價格）
      const fill = marketFill(order.side, q);
      if (fill != null && (order.side === "buy" ? fill <= limit : fill >= limit)) {
        const cost = await execute(db, email, order, q, fill);
        return { ok: true, filled: true, ...order, name: q.name, price: fill, source: q.source, ...cost };
      }
    }
    return queueOrder(db, email, order, q, "limit", limit, ses, live);
  }

  if (!live) {
    // 非交易時間的市價單：跟券商一樣變成預約單，下一個交易日以開盤價成交
    const est = q.order_upper || q.price;
    if (order.side === "buy" && orderCost({ code: order.code, side: "buy", price: est, shares: order.shares }).total > player.cash) {
      throw new PublicError(`現金不足（預約市價買單以漲停價 ${est} 預估）`);
    }
    return queueOrder(db, email, order, q, "market", 0, ses, false);
  }
  const fill = marketFill(order.side, q);
  if (fill == null) throw new PublicError(order.side === "buy" ? "漲停鎖住、沒有賣單，現在買不到" : "跌停鎖住、沒有買單，現在賣不掉");
  const cost = await execute(db, email, order, q, fill);
  return { ok: true, filled: true, ...order, name: q.name, price: fill, source: q.source, ...cost };
}

// 掛著的委託：每次看帳戶時檢查（不用一直開著網頁）。
// 用當天的開高低判斷「下單之後有沒有碰到委託價」；交易日結束還沒成交就失效；遇到休市日自動順延
async function matchOrders(db, email, quotes) {
  const { results: open } = await db.prepare("SELECT * FROM sim_orders WHERE email = ? AND status = 'open'").bind(email).all();
  if (!open.length) return;
  const now = new Date().toISOString();
  const prices = await priceMap([...new Set(open.map((o) => o.code))], quotes);
  for (const o of open) {
    const q = prices[o.code];
    // 舊版限價單沒有 kind／session：當成當天的限價單
    const ord = { ...o, kind: o.kind || "limit", session: o.session || taipeiDay(Date.parse(o.ts)) };
    const fill = q && !q.stale ? decideFill(ord, q) : null;
    if (fill) {
      let status = "filled", note = `${fill.note} ${fill.price}`;
      try {
        await execute(db, email, ord, q, fill.price);
      } catch (exc) {
        status = "failed"; note = exc instanceof PublicError ? exc.message : "成交失敗";
      }
      await db.prepare("UPDATE sim_orders SET status = ?, note = ? WHERE id = ? AND status = 'open'").bind(status, note, o.id).run();
    } else if (now > o.expires) {
      if (q && !q.stale && q.day < ord.session) {
        // 那天沒開盤（國定假日）：順延到下一個平日
        const day = nextWeekday(ord.session);
        await db.prepare("UPDATE sim_orders SET session = ?, expires = ? WHERE id = ? AND status = 'open'").bind(day, closeAt(day), o.id).run();
      } else {
        await db.prepare("UPDATE sim_orders SET status = 'expired', note = '當日未成交，委託失效' WHERE id = ? AND status = 'open'").bind(o.id).run();
      }
    }
  }
}

// 帳戶頁上方的狀態列：交易時段、報價資料日與時間（用台積電當參考，讀不到就看持股的報價）
async function sessionInfo(prices) {
  const ref = (await misQuotes(["2330"]))["2330"] || Object.values(prices).find((p) => p.day);
  const s = session(Date.now(), ref?.day);
  return {
    market_open: s.open, session: s.label, next_day: s.next,
    price_date: ref?.day || null,
    price_time: ref?.time ? new Date(Date.parse(ref.time) + 8 * 3600_000).toISOString().slice(11, 19) : null,
  };
}

async function account(db, email) {
  await ensurePlayer(db, email);
  const quotes = await getQuotes();
  await matchOrders(db, email, quotes);
  const player = await db.prepare("SELECT * FROM players WHERE email = ?").bind(email).first();
  const [{ results: holdings }, { results: trades }, { results: orders }, realized] = await Promise.all([
    db.prepare("SELECT code, name, shares, cost FROM holdings WHERE email = ?").bind(email).all(),
    db.prepare("SELECT ts, code, name, side, shares, price, amount, fee, tax, price_date FROM trades WHERE email = ? ORDER BY id DESC LIMIT 50").bind(email).all(),
    db.prepare("SELECT id, ts, code, name, side, shares, limit_price, status, note, expires, kind, session FROM sim_orders WHERE email = ? ORDER BY id DESC LIMIT 30").bind(email).all(),
    db.prepare("SELECT COALESCE(SUM(realized), 0) AS total FROM sim_realized WHERE email = ?").bind(email).first(),
  ]);
  const prices = { ...quotes, ...(await priceMap(holdings.map((h) => h.code), quotes)) };
  const { rows, value } = valuate(holdings, prices);
  for (const r of rows) {
    r.source = prices[r.code]?.source || "收盤";
    r.day_pct = prices[r.code]?.pct ?? null;
  }
  const total = player.cash + value;
  await db.prepare("INSERT INTO sim_equity (email, date, total) VALUES (?, ?, ?) ON CONFLICT (email, date) DO UPDATE SET total = excluded.total")
    .bind(email, taipeiDate(), Math.round(total)).run();
  const { results: equity } = await db.prepare("SELECT date, total FROM sim_equity WHERE email = ? ORDER BY date DESC LIMIT 120").bind(email).all();
  equity.reverse();
  const prev = equity.length > 1 ? equity[equity.length - 2].total : INITIAL_CASH;
  return {
    nickname: player.nickname, initial: INITIAL_CASH,
    cash: player.cash, holdings_value: value, total, return_pct: (total - INITIAL_CASH) / INITIAL_CASH,
    day_pl: total - prev, realized: realized.total, resets: player.resets,
    holdings: rows, trades, orders, equity,
    ...(await sessionInfo(prices)),
  };
}

async function watchlist(db, email, quotes) {
  const { results } = await db.prepare("SELECT code FROM sim_watch WHERE email = ? ORDER BY added").bind(email).all();
  const codes = results.map((r) => r.code).filter((c) => quotes[c]);
  const prices = await priceMap(codes, quotes);
  const signals = await Promise.all(codes.map((c) => chart(c, quotes).then((x) => x.signals).catch(() => null)));
  return { rows: codes.map((c, i) => ({ ...prices[c], signals: signals[i] })) };
}

async function leaderboard(db, email) {
  const [{ results: players }, { results: holdings }, { results: counts }, quotes] = await Promise.all([
    db.prepare("SELECT email, nickname, cash FROM players").all(),
    db.prepare("SELECT email, code, name, shares, cost FROM holdings").all(),
    db.prepare("SELECT email, COUNT(*) AS n FROM trades GROUP BY email").all(),
    getQuotes(),
  ]);
  const byEmail = {};
  for (const h of holdings) (byEmail[h.email] ||= []).push(h);
  const tradeCount = Object.fromEntries(counts.map((c) => [c.email, c.n]));
  const prices = { ...quotes, ...(await priceMap([...new Set(holdings.map((h) => h.code))], quotes)) };
  const rows = players.map((p) => {
    const { value } = valuate(byEmail[p.email] || [], prices);
    const total = p.cash + value;
    return {
      nickname: p.nickname, total, return_pct: (total - INITIAL_CASH) / INITIAL_CASH,
      holdings: (byEmail[p.email] || []).length, trades: tradeCount[p.email] || 0,
      me: p.email === email,
    };
  });
  rows.sort((a, b) => b.total - a.total);
  return { rows };
}

export async function onRequest({ request, env, params }) {
  const email = await accessEmail(request, env);
  if (!email) return json({ error: "需要先登入" }, 401);
  if (!env.DB) return json({ error: "模擬交易資料庫尚未設定" }, 503);

  const db = env.DB;
  const url = new URL(request.url);
  const route = [].concat(params.route || []).join("/");
  const method = request.method;
  const code = () => String(url.searchParams.get("code") || "").trim().toUpperCase();
  try {
    if (method === "GET" && route === "me") return json(await account(db, email));
    if (method === "GET" && route === "search") return json({ rows: searchStocks(await getQuotes(), url.searchParams.get("q")) });
    if (method === "GET" && route === "quote") return json(await quoteOf(code(), await getQuotes()));
    if (method === "GET" && route === "chart") return json(await chart(code(), await getQuotes()));
    if (method === "GET" && route === "leaderboard") return json(await leaderboard(db, email));
    if (method === "GET" && route === "watch") return json(await watchlist(db, email, await getQuotes()));
    if (method === "POST" && route === "order") return json(await placeOrder(db, email, await request.json()));
    if (method === "POST" && route === "cancel") {
      const id = Number((await request.json())?.id);
      const r = await db.prepare("UPDATE sim_orders SET status = 'cancelled', note = '自行取消' WHERE id = ? AND email = ? AND status = 'open'").bind(id, email).run();
      if (!r.meta.changes) throw new PublicError("這筆委託已經成交或不存在");
      return json({ ok: true });
    }
    if (method === "POST" && route === "watch") {
      const body = await request.json();
      const c = String(body?.code || "").trim().toUpperCase();
      if (!(await getQuotes())[c]) throw new PublicError("找不到這檔股票");
      if (body?.on === false) {
        await db.prepare("DELETE FROM sim_watch WHERE email = ? AND code = ?").bind(email, c).run();
      } else {
        const n = await db.prepare("SELECT COUNT(*) AS n FROM sim_watch WHERE email = ?").bind(email).first();
        if (n.n >= 30) throw new PublicError("自選股最多 30 檔");
        await db.prepare("INSERT OR IGNORE INTO sim_watch (email, code, added) VALUES (?, ?, ?)").bind(email, c, new Date().toISOString()).run();
      }
      return json({ ok: true });
    }
    if (method === "POST" && route === "nickname") {
      const nickname = String((await request.json())?.nickname || "").trim().slice(0, 20);
      if (!nickname) throw new PublicError("暱稱不能是空的");
      await ensurePlayer(db, email);
      await db.prepare("UPDATE players SET nickname = ? WHERE email = ?").bind(nickname, email).run();
      return json({ ok: true, nickname });
    }
    if (method === "POST" && route === "reset") {
      await ensurePlayer(db, email);
      await db.batch([
        db.prepare("DELETE FROM holdings WHERE email = ?").bind(email),
        db.prepare("DELETE FROM trades WHERE email = ?").bind(email),
        db.prepare("DELETE FROM sim_orders WHERE email = ?").bind(email),
        db.prepare("DELETE FROM sim_equity WHERE email = ?").bind(email),
        db.prepare("DELETE FROM sim_realized WHERE email = ?").bind(email),
        db.prepare("UPDATE players SET cash = ?, resets = resets + 1 WHERE email = ?").bind(INITIAL_CASH, email),
      ]);
      return json({ ok: true });
    }
    return json({ error: "找不到這個功能" }, 404);
  } catch (exc) {
    if (exc instanceof PublicError) return json({ error: exc.message }, exc.status);
    if (exc instanceof SyntaxError) return json({ error: "資料格式不正確" }, 400);
    console.error(exc);
    return json({ error: "系統錯誤，請稍後再試" }, 500);
  }
}
