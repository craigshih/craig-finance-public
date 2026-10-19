// 專屬投資顧問（訪客版，/robot/）的用量規則。所有登入網站的人都能直接用，不用通關語。
// Groq 免費額度是全站共用的，所以訪客有兩道上限：每人每天題數、全體訪客每天的 token 總量；
// 站長版（/portfolio/api/advisor）不受限制，訪客用到上限後剩下的額度都留給站長。

export const DAILY_LIMIT = 10;              // 每人每天最多幾題
export const LINE_DAILY_LIMIT = 5;          // LINE 機器人：每位朋友每天最多幾題（跟網站分開算，token 總量共用）
export const LINE_CHAT_LIMIT = 30;          // LINE 機器人：每位朋友每天最多聊幾句（閒聊回嗆，跟投資問答分開算）
export const GUEST_DAILY_TOKENS = 80_000;   // 全體訪客每天最多用多少 token（可用環境變數 ROBOT_DAILY_TOKENS 調整）
export const TOKENS_ROW = "_tokens";        // robot_usage 裡記全體訪客 token 的那一列

export function guestBlocked({ mine = 0, tokens = 0 }, env = {}, limit = DAILY_LIMIT) {
  const cap = Number(env.ROBOT_DAILY_TOKENS) || GUEST_DAILY_TOKENS;
  if (tokens >= cap) return "今天訪客的 AI 額度已經用完（要留一些給站長），明天再來";
  if (mine >= limit) return `每人每天最多 ${limit} 題，明天再來`;
  return null;
}
