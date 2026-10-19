// 專屬投資顧問（訪客版）：POST /robot/api/advisor
// 跟站長版同一套分析，但不帶持股、不寫入每日追蹤清單，並有每人每天題數與全體訪客 token 上限（見 _lib/robot.js）。
import { handleAdvisor } from "../../_lib/advisor_api.js";
import { guestQuota } from "../../_lib/robot_quota.js";

export async function onRequestPost(ctx) {
  const q = await guestQuota(ctx.request, ctx.env);
  return handleAdvisor(ctx, { dataPath: "/robot/stocks.json", holdingsPath: null, guest: true, ...q });
}
