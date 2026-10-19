// 選股機器人（站長版）：POST /portfolio/api/finder，在投資頁密碼後面；會標出已經持有的股票。
import { handleFinder } from "../../_lib/finder_api.js";

export const onRequestPost = (ctx) => handleFinder(ctx, {
  dataPath: "/portfolio/advisor/stocks.json", holdingsPath: "/portfolio/advisor/holdings.json",
});
