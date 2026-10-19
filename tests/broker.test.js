// 模擬交易的證券商規則：升降單位、漲跌停、交易時段、整股零股、委託撮合
import assert from "node:assert/strict";
import { test } from "node:test";

import { decideFill, limitBand, marketFill, onTick, orderSession, session, shareRule, tickSize } from "../functions/_lib/broker.js";

const T = (iso) => Date.parse(iso); // 帶時區的時間字串

test("升降單位：股票六級、ETF 兩級", () => {
  assert.equal(tickSize(9.99, "1101"), 0.01);
  assert.equal(tickSize(49.95, "2303"), 0.05);
  assert.equal(tickSize(88, "2412"), 0.1);
  assert.equal(tickSize(250, "2317"), 0.5);
  assert.equal(tickSize(999, "2454"), 1);
  assert.equal(tickSize(2490, "2330"), 5);
  assert.equal(tickSize(35, "0056"), 0.01);
  assert.equal(tickSize(113, "0050"), 0.05);
  assert.ok(onTick(2495, "2330"));
  assert.ok(!onTick(2492, "2330"));
  assert.ok(onTick(113.05, "0050"));
  assert.ok(!onTick(113.02, "0050"));
});

test("漲跌停 ±10%，取到合法價位（對照證交所實際數字）", () => {
  assert.deepEqual(limitBand(2490, "2330"), { upper: 2735, lower: 2245 });
  assert.deepEqual(limitBand(112.4, "0050"), { upper: 123.6, lower: 101.2 });
  assert.deepEqual(limitBand(1015, "6488"), { upper: 1115, lower: 914 });
});

test("整股與零股要分開下單", () => {
  assert.equal(shareRule(1000), null);
  assert.equal(shareRule(3000), null);
  assert.equal(shareRule(999), null);
  assert.match(shareRule(1500), /分開下單/);
});

test("交易時段：盤中、收盤後、週末、國定假日", () => {
  assert.equal(session(T("2026-10-14T10:00:00+08:00"), "2026-10-14").label, "盤中");
  const after = session(T("2026-10-14T15:30:00+08:00"), "2026-10-14");
  assert.equal(after.open, false);
  assert.equal(after.next, "2026-10-15");
  assert.equal(session(T("2026-10-14T08:00:00+08:00"), "2026-10-13").next, "2026-10-14"); // 開盤前：今天
  assert.equal(session(T("2026-10-17T11:00:00+08:00"), "2026-10-16").label, "休市");       // 週六
  const holiday = session(T("2026-10-09T10:00:00+08:00"), "2026-10-08");                     // 平日但報價停在前一天
  assert.equal(holiday.label, "休市");
  assert.equal(holiday.next, "2026-10-12");
  assert.equal(orderSession(T("2026-10-16T14:00:00+08:00"), "2026-10-16").day, "2026-10-19"); // 週五收盤後 → 週一預約單
});

test("市價單：買吃賣價、賣吃買價；漲停鎖住買不到", () => {
  const q = { price: 100, ask: 100.5, bid: 100, upper: 110, lower: 90 };
  assert.equal(marketFill("buy", q), 100.5);
  assert.equal(marketFill("sell", q), 100);
  assert.equal(marketFill("buy", { price: 110, ask: null, bid: 110, upper: 110, lower: 90 }), null);
  assert.equal(marketFill("sell", { price: 90, ask: 90, bid: null, upper: 110, lower: 90 }), null);
});

test("預約單：開盤價成交；限價看開盤價，沒到價就看盤中高低", () => {
  const day = "2026-10-15";
  const q = { day, open: 101, high: 105, low: 98, price: 103, ask: 103.5, bid: 103 };
  assert.deepEqual(decideFill({ kind: "market", side: "buy", session: day, seen_high: null }, q), { price: 101, note: "開盤價成交" });
  assert.deepEqual(decideFill({ kind: "limit", side: "buy", limit_price: 102, session: day, seen_high: null }, q), { price: 101, note: "開盤價成交" });
  assert.deepEqual(decideFill({ kind: "limit", side: "buy", limit_price: 99, session: day, seen_high: null }, q), { price: 99, note: "到價成交" });
  assert.equal(decideFill({ kind: "limit", side: "buy", limit_price: 97, session: day, seen_high: null }, q), null);
  assert.equal(decideFill({ kind: "market", side: "buy", session: "2026-10-16", seen_high: null }, q), null); // 還沒到委託交易日
});

test("盤中掛的限價單：下單前的高低點不算，之後創新低碰到才成交", () => {
  const day = "2026-10-15";
  const o = { kind: "limit", side: "buy", limit_price: 99, session: day, seen_high: 105, seen_low: 98 };
  assert.equal(decideFill(o, { day, open: 101, high: 105, low: 98, price: 103, ask: 103.5, bid: 103 }), null); // 98 是下單前的低點
  assert.deepEqual(decideFill(o, { day, open: 101, high: 105, low: 98, price: 99, ask: 99, bid: 98.9 }), { price: 99, note: "成交" }); // 賣價回到 99
  const sell = { kind: "limit", side: "sell", limit_price: 106, session: day, seen_high: 105, seen_low: 98 };
  assert.deepEqual(decideFill(sell, { day, open: 101, high: 106.5, low: 98, price: 104, ask: 104.5, bid: 104 }), { price: 106, note: "到價成交" });
});
