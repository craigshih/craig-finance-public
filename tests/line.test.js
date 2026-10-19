// LINE 機器人：webhook 簽章驗證、「今日一檔」關鍵字
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";

import { ASK_WORDS, validSignature } from "../functions/_lib/line.js";

test("簽章正確才放行，竄改內容或沒有簽章都拒絕", async () => {
  const secret = "test-channel-secret";
  const body = JSON.stringify({ events: [{ type: "join", source: { type: "group", groupId: "Cabc" } }] });
  const sig = createHmac("sha256", secret).update(body).digest("base64");
  assert.ok(await validSignature(secret, body, sig));
  assert.ok(!(await validSignature(secret, body.replace("join", "leave"), sig)));
  assert.ok(!(await validSignature(secret, body, "")));
  assert.ok(!(await validSignature("", body, sig)));
});

test("群組裡打「今日一檔」才回覆，聊天內容提到一檔不會誤觸發", () => {
  for (const t of ["今日一檔", "每日一檔", "今日一檔？", "一檔!"]) assert.ok(ASK_WORDS.test(t), t);
  for (const t of ["今天那一檔不錯", "今日一檔怎麼還沒來", "hello"]) assert.ok(!ASK_WORDS.test(t), t);
});

// ---------- 互動：指令、查價、AI 問答 ----------
import {
  HELP_WORDS, MARKET_WORDS, clock, formatAnswer, formatIndices, formatQuote, quoteCodes, stripMention,
} from "../functions/_lib/line.js";
import { ALIASES } from "../functions/_lib/advisor.js";

const STOCKS = {
  "2330": { code: "2330", name: "台積電", market: "上市" },
  "2317": { code: "2317", name: "鴻海", market: "上市" },
  "4958": { code: "4958", name: "臻鼎-KY", market: "上市" },
};

test("說明、大盤：整句符合才觸發", () => {
  for (const t of ["說明", "說明？", "help", "功能"]) assert.ok(HELP_WORDS.test(t), t);
  for (const t of ["大盤", "大盤?", "盤勢"]) assert.ok(MARKET_WORDS.test(t), t);
  for (const t of ["大盤今天跌好多", "說明一下你昨天講的"]) assert.ok(!HELP_WORDS.test(t) && !MARKET_WORDS.test(t), t);
});

test("@機器人 從訊息拿掉；@ 別人不算", () => {
  const msg = { text: "@財經小幫手 什麼是本益比？", mention: { mentionees: [{ index: 0, length: 6, isSelf: true }] } };
  assert.deepEqual(stripMention(msg), { text: "什麼是本益比？", mentioned: true });
  const other = { text: "@小明 2330", mention: { mentionees: [{ index: 0, length: 3, isSelf: false }] } };
  assert.deepEqual(stripMention(other), { text: "@小明 2330", mentioned: false });
  assert.deepEqual(stripMention({ text: " 2330 " }), { text: "2330", mentioned: false });
});

test("查價：代號、名稱、簡稱、多檔；一般聊天不會被當成查價", () => {
  assert.deepEqual(quoteCodes("2330", STOCKS, ALIASES), ["2330"]);
  assert.deepEqual(quoteCodes("台積電", STOCKS, ALIASES), ["2330"]);
  assert.deepEqual(quoteCodes("台積", STOCKS, ALIASES), ["2330"]);
  assert.deepEqual(quoteCodes("臻鼎", STOCKS, ALIASES), ["4958"]);
  assert.deepEqual(quoteCodes("查 2330 鴻海", STOCKS, ALIASES), ["2330", "2317"]);
  assert.deepEqual(quoteCodes("鴻海股價？", STOCKS, ALIASES), ["2317"]);
  assert.deepEqual(quoteCodes("2330、2317、2330", STOCKS, ALIASES), ["2330", "2317"]);
  for (const t of ["台積電今天好猛", "晚上吃什麼", "", "2330 是什麼公司", "1 2 3"]) assert.equal(quoteCodes(t, STOCKS, ALIASES), null, t);
  assert.equal(quoteCodes("1101 1102 1103 1104 1105 1216", STOCKS, ALIASES), null); // 一次最多 5 檔
});

test("時間取到 5 分鐘、不顯示秒；不是今天就標日期", () => {
  const now = Date.parse("2026-10-19T05:00:00Z"); // 台北 13:00
  assert.equal(clock("2026-10-19T02:27:31Z", now), "今天 10:25");
  assert.equal(clock("2026-10-17T05:30:00Z", now), "10/17 13:30");
  assert.equal(clock(null, now), "");
});

test("報價格式：漲跌、漲停、開高低量", () => {
  const now = Date.parse("2026-10-19T03:00:00Z");
  const q = { price: 1085, prev: 1070, chg: 15, pct: 1.4, open: 1070, high: 1090, low: 1065, volume: 23456, market: "上市", name: "台積電", time: "2026-10-19T02:31:00Z" };
  assert.equal(formatQuote("2330", q, STOCKS, now), "📈 台積電 2330（上市）\n1,085 元　▲15（+1.40%）\n開 1,070　高 1,090　低 1,065　量 23,456 張\n🕒 今天 10:30");
  assert.match(formatQuote("2317", { price: 99, prev: 110, chg: -11, pct: -10, lower: 99 }, STOCKS, now), /鴻海 2317\n99 元　▼11（-10.00%） 跌停/);
  assert.match(formatQuote("2317", { price: 110, prev: 110, chg: 0, pct: 0 }, STOCKS, now), /平盤/);
});

test("大盤格式：照固定順序，沒資料時有說明", () => {
  const idx = {
    "^SOX": { name: "費城半導體", price: 5000, chg: -50, pct: -0.99, time: "2026-10-18T20:00:00Z" },
    "^TWII": { name: "台股加權", price: 23456.78, chg: 123.4, pct: 0.53, time: "2026-10-19T05:30:00Z" },
  };
  const out = formatIndices(idx, Date.parse("2026-10-19T06:00:00Z"));
  assert.equal(out, "🌏 大盤與國際指數\n台股加權　23,456.78　▲0.53%\n費城半導體　5,000　▼0.99%\n🕒 今天 13:30");
  assert.match(formatIndices({}), /抓不到/);
});

test("AI 回答濃縮：名詞解釋與個股分析都有免責聲明", () => {
  const coach = formatAnswer({ answer: { mode: "coach", headline: "本益比＝股價 ÷ 每股盈餘", coach: "白話說明", follow_ups: ["a", "b", "c"] }, data_date: "2026-10-19T00:00:00Z" });
  assert.match(coach, /^💬 本益比＝股價 ÷ 每股盈餘\n\n白話說明\n\n👉 可以再問：a／b\n\n※ AI 依公開資料整理.*（資料日 2026-10-19）$/);
  const stock = formatAnswer({
    answer: { mode: "stock", headline: "偏保守", stocks: [{ code: "2330", stance: "偏保守", summary: "回撤大" }],
      synthesis: { conclusion: "先觀察", conditions: ["外資回補"] } },
    stocks: [{ code: "2330", name: "台積電" }], unverified: [12.3],
  });
  assert.match(stock, /先觀察\n\n・台積電（2330）偏保守：回撤大\n\n🔄 什麼情況會改變看法\n・外資回補\n\n⚠️ 回答裡有 1 個數字/);
  assert.ok(stock.endsWith("不構成投資建議。"));
});

// ---------- 韭菜仔人設 ----------
import { callName, formatChat, fortune, isAnalysis } from "../functions/_lib/persona.js";

test("叫名字：開頭的名字拿掉，句中的名字整句保留", () => {
  assert.deepEqual(callName("韭菜仔，2330"), { text: "2330", called: true });
  assert.deepEqual(callName("韭菜仔"), { text: "", called: true });
  assert.deepEqual(callName("你這韭菜仔很廢"), { text: "你這韭菜仔很廢", called: true });
  assert.deepEqual(callName("今天好熱"), { text: "今天好熱", called: false });
});

test("點名股票而且在問問題才算分析題", () => {
  assert.ok(isAnalysis("台積電值得買嗎", ["2330"]));
  assert.ok(!isAnalysis("台積電害我住套房", ["2330"]));
  assert.ok(!isAnalysis("什麼是本益比？", []));
});

test("聊天回答：拿掉引號與禁語，聊投資才加免責", () => {
  assert.equal(formatChat("你好爛", "「你才爛，被套還敢講話」"), "你才爛，被套還敢講話");
  assert.match(formatChat("ETF 是什麼", "一籃子股票啦"), /不構成投資建議/);
  assert.equal(formatChat("報明牌", "這檔保證穩賺。自己做功課啦。"), "自己做功課啦。");
});

test("抽籤：同一人同一天固定，換天會變（12 支籤至少抽到 2 種）", () => {
  const day = Date.parse("2026-10-19T03:00:00Z");
  assert.equal(fortune("U1", day), fortune("U1", day + 3600_000));
  const seen = new Set(Array.from({ length: 10 }, (_, i) => fortune("U1", day + i * 86400_000).split("\n")[1]));
  assert.ok(seen.size >= 2);
  assert.match(fortune("U1", day), /^🎋 今日股運（10\/19）/);
});
