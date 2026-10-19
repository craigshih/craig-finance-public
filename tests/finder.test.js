// 選股機器人的規則：條件清理、龍頭判斷、跌深加分、產業分散、點名的公司一定納入比較
import assert from "node:assert/strict";
import { test } from "node:test";

import { cleanSpec, industryRanks, pickStocks, vocab } from "../functions/_lib/finder.js";

const mk = (code, name, industry, mcap, extra = {}) => ({
  code, name, market: "上市", industry, close: 100, mcap_yi: mcap,
  valuation: { pe: 15, yield: 3, roe_est: 15, ...(extra.valuation || {}) }, revenue: { yoy: 10, ...(extra.revenue || {}) },
  margins: { gross: 30 }, risk: { chg_5d: -3, chg_20d: extra.chg20 ?? -5, vol_1y: 30 }, peers: extra.peers || [],
});
const S = Object.fromEntries([
  mk("2330", "台積電", "半導體業", 400000, { chg20: -8 }),
  mk("2454", "聯發科", "半導體業", 30000, { chg20: -15 }),
  mk("3711", "日月光投控", "半導體業", 20000, { chg20: -12 }),
  mk("2303", "聯電", "半導體業", 7000, { chg20: -20 }),        // 半導體第 4 大，不是龍頭
  mk("2881", "富邦金", "金融保險業", 12000, { chg20: -6, valuation: { yield: 5 } }),
  mk("2882", "國泰金", "金融保險業", 11000, { chg20: -9, valuation: { yield: 4.5 } }),
  mk("2891", "中信金", "金融保險業", 9000, { chg20: -4, valuation: { yield: 5.5 } }),
  mk("2886", "兆豐金", "金融保險業", 6000, { chg20: -3 }),
  mk("1301", "台塑", "塑膠工業", 5000, { chg20: -25, revenue: { yoy: -30 } }),  // 跌深但營收大衰退
  mk("9999", "虧損股", "其他業", 100, { valuation: { pe: null } }),
].map((s) => [s.code, s]));
const V = vocab(S);

test("條件清理：只留清單裡的產業、數量限制在 3～8", () => {
  const sp = cleanSpec({ industries: ["金融保險業", "不存在的業"], leaders: true, dip: "yes", count: 20 }, V);
  assert.deepEqual(sp.industries, ["金融保險業"]);
  assert.equal(sp.leaders, true);
  assert.equal(sp.dip, false); // 不是 true 就當 false
  assert.equal(sp.count, 8);
});

test("產業內市值排名", () => {
  const r = industryRanks(S);
  assert.equal(r["2330"], 1);
  assert.equal(r["2303"], 4);
  assert.equal(r["2881"], 1);
});

test("趁大跌找龍頭（點名聯發科、日月光，加上金融股）：只挑產業前三，點名的一定在，同產業最多 2 檔", () => {
  const spec = cleanSpec({ industries: ["金融保險業"], leaders: true, dip: true, count: 6 }, V);
  const picks = pickStocks(S, spec, ["2454", "3711"]).map((p) => p.code);
  assert.ok(picks.includes("2454") && picks.includes("3711"), picks.join());
  assert.ok(!picks.includes("2303"), "聯電不是龍頭");
  assert.ok(!picks.includes("2886"), "兆豐金不是金融前三");
  assert.ok(!picks.includes("9999"), "虧損股不選");
  const fin = picks.filter((c) => S[c].industry === "金融保險業");
  assert.ok(fin.length >= 1 && fin.length <= 2, `金融 ${fin.length} 檔`);
});

test("跌深加分，但營收大幅衰退的會被扣分", () => {
  const spec = cleanSpec({ dip: true, count: 3 }, V);
  const picks = pickStocks(S, spec, []);
  assert.ok(picks.every((p) => p.reasons.some((r) => r.startsWith("近 5 日"))));
  assert.notEqual(picks[0].code, "1301", "台塑跌最多但營收衰退 30%，不該排第一");
});

test("只選一個產業時不限 2 檔", () => {
  const spec = cleanSpec({ industries: ["金融保險業"], dividend: true, count: 4 }, V);
  const picks = pickStocks(S, spec, []);
  assert.equal(picks.length, 4);
  assert.equal(picks[0].code, "2891", "殖利率最高的中信金排前面");
});
