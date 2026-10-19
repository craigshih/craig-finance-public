// node --test tests/：模擬交易 v2 的搜尋、盤中時間、限價期限、四指標體檢。
import assert from "node:assert/strict";
import { test } from "node:test";

import { marketOpen, nextClose, searchStocks } from "../functions/_lib/market.js";
import { computeSignals, maSeries, parseYahooChart } from "../functions/_lib/signals.js";

const Q = {
  "2330": { code: "2330", name: "台積電", market: "上市", price: 1000 },
  "2303": { code: "2303", name: "聯電", market: "上市", price: 50 },
  "0050": { code: "0050", name: "元大台灣50", market: "上市", price: 100 },
  "0056": { code: "0056", name: "元大高股息", market: "上市", price: 30 },
  "3711": { code: "3711", name: "日月光投控", market: "上市", price: 150 },
};

test("用名稱或代號搜股票", () => {
  assert.deepEqual(searchStocks(Q, "台積").map((r) => r.code), ["2330"]);
  assert.deepEqual(searchStocks(Q, "元大").map((r) => r.code), ["0050", "0056"]);
  assert.deepEqual(searchStocks(Q, "2330").map((r) => r.code), ["2330"]);
  assert.deepEqual(searchStocks(Q, "投控").map((r) => r.code), ["3711"]);
  assert.deepEqual(searchStocks(Q, "  "), []);
});

test("台股盤中時間（台北 09:00～13:30，平日）", () => {
  assert.equal(marketOpen(new Date("2026-10-08T02:00:00Z")), true);   // 週四 10:00
  assert.equal(marketOpen(new Date("2026-10-08T06:00:00Z")), false);  // 週四 14:00
  assert.equal(marketOpen(new Date("2026-10-10T02:00:00Z")), false);  // 週六
});

test("限價委託期限：當天 13:30，收盤後或週末順延到下一個平日", () => {
  assert.equal(nextClose(new Date("2026-10-08T02:00:00Z")), "2026-10-08T05:30:00.000Z");
  assert.equal(nextClose(new Date("2026-10-08T07:00:00Z")), "2026-10-09T05:30:00.000Z");
  assert.equal(nextClose(new Date("2026-10-09T07:00:00Z")), "2026-10-12T05:30:00.000Z"); // 週五收盤後 → 週一
});

const series = (n, f, vol = () => 1000) => Array.from({ length: n }, (_, i) => {
  const c = f(i);
  return { date: `d${i}`, open: c, high: c * 1.01, low: c * 0.99, close: c, volume: vol(i) };
});

test("四指標：均線多頭排列＋量能溫和放大＝可加入觀察名單", () => {
  const rows = series(80, (i) => 100 + i, (i) => (i === 79 ? 1600 : 1000));
  const s = computeSignals(rows);
  assert.equal(s.trend, "多頭排列");
  assert.equal(s.volume, "放大");
  assert.equal(s.verdict, "watch");
});

test("四指標：均線破位＋量能下滑＝先撤退再說；爆量另外提醒", () => {
  const down = series(80, (i) => 200 - i, (i) => (i >= 75 ? 600 : 1000));
  const s = computeSignals(down);
  assert.equal(s.trend, "空頭排列");
  assert.equal(s.verdict, "retreat");
  const burst = computeSignals(series(80, (i) => 100 + i, (i) => (i === 79 ? 4000 : 1000)));
  assert.equal(burst.volume, "爆量");
  assert.equal(burst.verdict, "neutral");
  assert.equal(computeSignals(series(30, () => 1)), null);
});

test("均線與 Yahoo 日 K 解析", () => {
  assert.deepEqual(maSeries(series(6, (i) => i + 1), 5).slice(3), [null, 3, 4]);
  const rows = parseYahooChart({ chart: { result: [{ meta: { gmtoffset: 28800 }, timestamp: [1791336600],
    indicators: { quote: [{ open: [1], high: [2], low: [0.5], close: [1.5], volume: [100] }] } }] } });
  assert.equal(rows[0].close, 1.5);
  assert.equal(rows.length, 1);
});
