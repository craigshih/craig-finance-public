// 選股機器人的共用處理：站長版（/portfolio/api/finder，會標出已持有）與訪客版（/robot/api/finder）。

import { MAX_QUESTION, collectNumbers, compactStock, findStocks, scrub, unverifiedNumbers } from "./advisor.js";
import { askGroq, loadData } from "./advisor_api.js";
import { EXPLAIN_PROMPT, cleanSpec, pickStocks, specPrompt, vocab } from "./finder.js";

const fail = (error, status = 400) => Response.json({ error }, { status });

export async function handleFinder({ request, env }, opts) {
  let body;
  try {
    body = await request.json();
  } catch {
    return fail("格式不正確");
  }
  const question = String(body?.question || "").trim();
  if (!question) return fail("請描述你想找什麼樣的股票");
  if (question.length > MAX_QUESTION) return fail(`請在 ${MAX_QUESTION} 字以內`);
  const { data, holdings } = await loadData(env, request, opts.dataPath, opts.holdingsPath);
  if (!data) return fail("今天的資料還沒產生，請等下一次網站更新", 503);
  if (!env.GROQ_API_KEY) return fail("AI 金鑰還沒設定（GROQ_API_KEY），暫時無法回答", 503);
  if (opts.beforeAsk) {
    const blocked = await opts.beforeAsk();
    if (blocked) return blocked;
  }

  let used = 0;
  try {
    // 1. 一句話 → 條件
    const v = vocab(data.stocks);
    const s1 = await askGroq(env, [{ role: "user", content: specPrompt(question, v) }], { max: 900, effort: "low" });
    used += s1.tokens;
    const spec = cleanSpec(s1.raw, v);
    const mentioned = [...new Set([...findStocks(question, data.stocks), ...findStocks(spec.names.join(" "), data.stocks)])];

    // 2. 規則挑股
    const picks = pickStocks(data.stocks, spec, mentioned);
    if (!picks.length) {
      return Response.json({ spec, picks: [], intro: "照這些條件找不到符合的股票，可以把條件放寬一點再試（例如不限產業或不限龍頭）。", cautions: [] });
    }

    // 3. AI 寫理由（只能用挑出來這幾檔的資料）
    const held = Object.fromEntries((holdings?.holdings || []).map((h) => [h.code, h]));
    const ctx = {
      question, intent: spec.intent,
      picks: picks.map((p) => ({ ...compactStock(data.stocks[p.code], held[p.code]), industry_rank_by_mcap: p.rank,
        market_cap_yi: data.stocks[p.code].mcap_yi ?? null, rule_reasons: p.reasons })),
    };
    const s2 = await askGroq(env, [{ role: "system", content: EXPLAIN_PROMPT }, { role: "user", content: `DATA:\n${JSON.stringify(ctx)}` }],
      { max: 2600, effort: "low" });
    used += s2.tokens;
    const byCode = Object.fromEntries((Array.isArray(s2.raw?.picks) ? s2.raw.picks : []).map((x) => [String(x.code), x]));
    const answer = {
      intro: scrub(s2.raw?.intro, 120),
      picks: picks.map((p) => ({ code: p.code, why: scrub(byCode[p.code]?.why, 200), watch: scrub(byCode[p.code]?.watch, 120) })),
      cautions: (Array.isArray(s2.raw?.cautions) ? s2.raw.cautions : []).map((x) => scrub(x, 100)).filter(Boolean).slice(0, 3),
    };
    const s = (c) => data.stocks[c];
    return Response.json({
      spec, ...answer,
      unverified: unverifiedNumbers(answer, [...collectNumbers(ctx), 5, 10, 20, 60, 120, 240]), // 均線天數不是資料數字
      cards: picks.map((p) => ({
        code: p.code, name: s(p.code).name, market: s(p.code).market, industry: s(p.code).industry, rank: p.rank, reasons: p.reasons,
        close: s(p.code).close, mcap_yi: s(p.code).mcap_yi ?? null, chg_5d: s(p.code).risk?.chg_5d ?? null, chg_20d: s(p.code).risk?.chg_20d ?? null,
        pe: s(p.code).valuation?.pe ?? null, yield: s(p.code).valuation?.yield ?? null, roe: s(p.code).valuation?.roe_est ?? null,
        rev_yoy: s(p.code).revenue?.yoy ?? null, gross: s(p.code).margins?.gross ?? null, held: held[p.code] ? true : false,
      })),
      data_date: data.generated_at,
    });
  } catch (exc) {
    console.error(exc);
    return fail("AI 暫時沒有回應，請稍後再試", 502);
  } finally {
    if (opts.afterAsk && used) await opts.afterAsk(used).catch(() => {});
  }
}
