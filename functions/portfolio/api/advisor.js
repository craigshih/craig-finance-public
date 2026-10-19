// AI 投資顧問（站長版）：POST /portfolio/api/advisor  { question, history: [{q, headline}] }
// 在 /portfolio/ 底下，先經過投資頁的密碼檢查（functions/portfolio/_middleware.js），會帶入站長持股權重。

import { handleAdvisor } from "../../_lib/advisor_api.js";

export const onRequestPost = (ctx) => handleAdvisor(ctx, {
  dataPath: "/portfolio/advisor/stocks.json", holdingsPath: "/portfolio/advisor/holdings.json", guest: false,
});
