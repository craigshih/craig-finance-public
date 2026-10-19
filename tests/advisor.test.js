// node --test tests/：AI 投資顧問的股票比對、回答清理、數字核對。
import assert from "node:assert/strict";
import { test } from "node:test";

import { backtestNotes, buildMessages, collectNumbers, compactStock, findStocks, parsePttIndex, pttFor, sanitizeAnswer, scrub, unverifiedNumbers } from "../functions/_lib/advisor.js";

const STOCKS = {
  "2330": { code: "2330", name: "台積電", market: "上市" },
  "2303": { code: "2303", name: "聯電", market: "上市" },
  "4958": { code: "4958", name: "臻鼎-KY", market: "上市" },
  "3008": { code: "3008", name: "大立光", market: "上市" },
  "0050": { code: "0050", name: "元大台灣50", market: "上市" },
  "6274": { code: "6274", name: "台燿", market: "上櫃" },
};

test("從問題找出股票：名稱、簡稱、代號，依出現順序", () => {
  assert.deepEqual(findStocks("台積電和聯電哪個比較值得投資？", STOCKS), ["2330", "2303"]);
  assert.deepEqual(findStocks("聯電 vs 台積", STOCKS), ["2303", "2330"]);
  assert.deepEqual(findStocks("臻鼎還值得續抱嗎", STOCKS), ["4958"]);
  assert.deepEqual(findStocks("6274 跟 0050 比較", STOCKS), ["6274", "0050"]);
  assert.deepEqual(findStocks("什麼是最大回撤？", STOCKS), []);
  assert.deepEqual(findStocks("2026 年展望", STOCKS), []); // 年份不是股票
});

test("名稱長的先比：大立光不會被拆成別的", () => {
  const s = { ...STOCKS, "9999": { code: "9999", name: "大立", market: "上市" } };
  assert.deepEqual(findStocks("大立光好嗎", s), ["3008"]);
});

test("禁語整句拿掉", () => {
  assert.equal(scrub("營收成長強勁。目標價 3000 元。風險在估值。"), "營收成長強勁。風險在估值。");
  assert.equal(scrub("這檔保證穩賺！"), "");
});

test("回答清理：未知代號與欄位丟掉、立場限定選項", () => {
  const a = sanitizeAnswer({
    mode: "compare", headline: "台積電較穩", stocks: [{ code: "2330", stance: "超看好", summary: "x" }, { code: "9999", stance: "偏正面" }],
    risk_camp: { stance: "偏保守", argument: "回撤大", points: ["a", "b", "c", "d", "e"] },
    synthesis: { conclusion: "c", ranking: [{ code: "2303", reason: "r" }, { code: "NVDA", reason: "x" }], conditions: [] },
    follow_ups: ["q1"],
  }, ["2330", "2303"]);
  assert.equal(a.stocks.length, 1);
  assert.equal(a.stocks[0].stance, "中性");
  assert.equal(a.risk_camp.points.length, 4);
  assert.equal(a.quant_camp, null);
  assert.deepEqual(a.synthesis.ranking.map((r) => r.code), ["2303"]);
});

test("數字核對：資料裡有的放行（含四捨五入、正負號），沒有的標出來", () => {
  const data = { risk: { mdd_1y: -41.8, var95_1d: -6.91 }, revenue: { yoy: 53.3 }, note: "站上 60 日線" };
  const known = collectNumbers(data);
  assert.ok(known.includes(60));
  const ans = { headline: "回撤 41.8%、VaR -6.9%，營收年增 53%", points: ["2026-08 營收", "本益比 45.2 倍", "連 3 天買超"] };
  assert.deepEqual(unverifiedNumbers(ans, known), ["45.2"]);
});

test("給 AI 的資料不含走勢陣列，持股只給權重", () => {
  const c = compactStock({ code: "2330", name: "台積電", market: "上市", risk: { mdd_1y: -10, spark: [1, 2, 3] } }, { weight_pct: 12.5, pl_pct: 30, cost: 999 });
  assert.equal(c.risk.spark, undefined);
  assert.deepEqual(c.my_position, { weight_pct: 12.5, pl_pct: 30 });
  const msgs = buildMessages({ question: "q", data: { stocks: [c] }, news: {}, history: [{ q: "前一題", headline: "h" }], portfolio: null });
  assert.equal(msgs[0].role, "system");
  assert.equal(msgs.length, 4);
  assert.ok(msgs.at(-1).content.includes("問題：q"));
});

test("PTT：解析看板列表、提及次數、[標的] 多空、回文不重複算", () => {
  const html = `<div class="title">
    <a href="/bbs/Stock/M.1.A.html">[標的] 2330 台積電 多</a></div>
    <div class="title"><a href="/bbs/Stock/M.2.A.html">Re: [新聞] 台積電擴產</a></div>
    <div class="title"><a href="/bbs/Stock/M.3.A.html">[新聞] 台積電擴產</a></div>
    <div class="title"><a href="/bbs/Stock/M.4.A.html">[標的] 2303 聯電 空</a></div>
    <a class="btn wide" href="/bbs/Stock/index100.html">&lsaquo; 上頁</a>`;
  const page = parsePttIndex(html);
  assert.equal(page.titles.length, 4);
  assert.equal(page.prev, "https://www.ptt.cc/bbs/Stock/index100.html");
  const tsmc = pttFor("2330", "台積電", page.titles);
  assert.equal(tsmc.mentions, 2);
  assert.equal(tsmc.target_bull, 1);
  assert.equal(pttFor("2303", "聯電", page.titles).target_bear, 1);
});

test("名詞解釋的舉例數字不檢查", () => {
  assert.deepEqual(unverifiedNumbers({ coach: "從 100 元跌到 60 元，回撤 40%", headline: "說明" }, []), []);
});

test("回測註記：規則落後買進持有時一定提醒", () => {
  const n = backtestNotes([{ name: "台積電", backtest: { strategy_cagr: 32.8, hold_cagr: 78.8 } }, { name: "聯電", backtest: { strategy_cagr: 30, hold_cagr: 20 } }]);
  assert.equal(n.length, 2);
  assert.ok(n[0].includes("台積電") && n[0].includes("落後"));
  assert.ok(n[1].includes("樣本內"));
  assert.deepEqual(backtestNotes([{ name: "x" }]), []);
});
