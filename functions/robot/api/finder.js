// 選股機器人（訪客版）：POST /robot/api/finder，跟顧問共用每人每天 10 題的額度。
import { handleFinder } from "../../_lib/finder_api.js";
import { guestQuota } from "../../_lib/robot_quota.js";

export async function onRequestPost(ctx) {
  const q = await guestQuota(ctx.request, ctx.env);
  return handleFinder(ctx, { dataPath: "/robot/stocks.json", holdingsPath: null, ...q });
}
