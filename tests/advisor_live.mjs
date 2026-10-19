// 部署前用真的 AI 試問一題（不含持股資料），把回答印在 Actions log，方便檢查品質。失敗不擋部署。
//   GROQ_API_KEY=... node tests/advisor_live.mjs "台積電和聯電哪個比較值得投資？"
import { readFileSync } from "node:fs";

import { buildMessages, collectNumbers, compactStock, findStocks, sanitizeAnswer, unverifiedNumbers } from "../functions/_lib/advisor.js";

const question = process.argv[2] || "台積電和聯電哪個比較值得投資？";
const data = JSON.parse(readFileSync("data/advisor/stocks.json", "utf8"));
const codes = findStocks(question, data.stocks);
const context = { generated_at: data.generated_at, stocks: codes.map((c) => compactStock(data.stocks[c], null)) };
const t0 = Date.now();
const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
  method: "POST",
  headers: { Authorization: `Bearer ${process.env.GROQ_API_KEY}`, "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "openai/gpt-oss-120b", messages: buildMessages({ question, data: context, news: {}, history: [], portfolio: null }),
    max_completion_tokens: 3500, reasoning_effort: "medium", temperature: 0.3, response_format: { type: "json_object" },
  }),
});
if (!res.ok) throw new Error(`Groq ${res.status} ${await res.text()}`);
const body = await res.json();
const answer = sanitizeAnswer(JSON.parse(body.choices[0].message.content), codes);
console.log(`問題：${question}（找到 ${codes.join(", ") || "無"}，${((Date.now() - t0) / 1000).toFixed(1)} 秒，${body.usage?.total_tokens} tokens）`);
console.log(JSON.stringify(answer, null, 1));
console.log("找不到出處的數字：", unverifiedNumbers(answer, [...collectNumbers(context), 15, 300, 60, 120, 20, 95, 52, 1.5, 3]));
