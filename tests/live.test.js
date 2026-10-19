// node --test tests/：盤中即時報價的解析。
import assert from "node:assert/strict";
import { test } from "node:test";

import { misChannels, parseMis, parseSpark, validCodes, validUs } from "../functions/_lib/live.js";

test("MIS：有成交用成交價；沒成交改用最後成交或買賣中間價；大盤代號轉成 ^TWII", () => {
  const q = parseMis({ msgArray: [
    { c: "2330", n: "台積電", z: "2585.0000", y: "2500.0000", tlong: "1791354600000" },
    { c: "6274", z: "-", pz: "-", y: "1700", b: "1710.0000_1705.0000_", a: "1720.0000_1725.0000_" },
    { c: "t00", z: "49806.37", y: "49822.55" },
    { c: "9999", z: "-", y: "-" },
  ] });
  assert.equal(q["2330"].price, 2585);
  assert.equal(q["2330"].pct, 3.4);
  assert.equal(q["6274"].price, 1715);
  assert.ok(q["^TWII"].chg < 0);
  assert.equal(q["9999"], undefined);
});

test("Yahoo spark 解析", () => {
  const q = parseSpark({ spark: { result: [{ symbol: "^SOX", response: [{ meta: { regularMarketPrice: 110, chartPreviousClose: 100, regularMarketTime: 1 } }] }] } });
  assert.equal(q["^SOX"].pct, 10);
});

test("代號檢查與上市櫃都查", () => {
  assert.deepEqual(validCodes("2330, 6274,abc,2330,00878"), ["2330", "6274", "00878"]);
  assert.deepEqual(misChannels(["2330"]), ["tse_2330.tw", "otc_2330.tw"]);
});

test("美股代號檢查", () => {
  assert.deepEqual(validUs("nvda, BRK.B,1234,AAPL,nvda"), ["NVDA", "BRK.B", "AAPL"]);
});
