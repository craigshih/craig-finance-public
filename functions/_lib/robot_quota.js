// 訪客版（/robot/）的用量：每人每天題數＋全體訪客每天 token 上限（規則在 robot.js）。顧問與選股共用同一份額度。
import { accessEmail } from "./auth.js";
import { hmacHex } from "./session.js";
import { LINE_DAILY_LIMIT, TOKENS_ROW, guestBlocked } from "./robot.js";

const taipeiDay = () => new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);

export async function guestQuota(request, env) {
  const who = (await accessEmail(request, env)) || request.headers.get("CF-Connecting-IP") || "anon";
  return quota(env, `robot:${who}`, undefined);
}

// LINE 機器人：用 LINE 的 userId 計算每人題數（只存雜湊），擋下時 beforeAsk 回傳一句話（不是 Response）
// kind："line"＝投資問答、"line-chat"＝閒聊，各算各的題數
export async function lineQuota(env, userId, kind = "line", limit = LINE_DAILY_LIMIT) {
  const q = await quota(env, `${kind}:${userId || "anon"}`, limit);
  return {
    ...q,
    beforeAsk: async () => {
      const blocked = await q.beforeAsk();
      return blocked ? (await blocked.json()).error : null;
    },
  };
}

async function quota(env, key, limit) {
  const day = taipeiDay();
  const id = (await hmacHex(env.SESSION_SECRET || "robot", key)).slice(0, 24); // 不存 email／LINE 帳號本身
  const bump = (w, by) => env.DB.prepare(
    "INSERT INTO robot_usage (day, who, n) VALUES (?, ?, ?) ON CONFLICT(day, who) DO UPDATE SET n = n + excluded.n",
  ).bind(day, w, by).run();
  return {
    beforeAsk: async () => {
      if (!env.DB) return null;
      const { results } = await env.DB.prepare("SELECT who, n FROM robot_usage WHERE day = ? AND who IN (?, ?)").bind(day, id, TOKENS_ROW).all();
      const get = (w) => results.find((r) => r.who === w)?.n || 0;
      const msg = guestBlocked({ mine: get(id), tokens: get(TOKENS_ROW) }, env, limit);
      if (msg) return Response.json({ error: msg }, { status: 429 });
      await bump(id, 1);
      return null;
    },
    afterAsk: async (tokens) => {
      if (env.DB && tokens) await bump(TOKENS_ROW, tokens);
    },
  };
}
