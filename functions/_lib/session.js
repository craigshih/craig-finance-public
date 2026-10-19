// 投資頁密碼：登入後發一個簽章過的 cookie，30 天有效。
// 簽章金鑰綁定 SESSION_SECRET 與密碼本身，所以改密碼會讓所有舊 cookie 立刻失效。

const enc = new TextEncoder();
export const COOKIE = "pf_session";
export const SESSION_DAYS = 30;

export async function hmacHex(key, msg) {
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(msg)));
  return [...sig].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// 長度相同的字串做固定時間比較，避免從回應時間推測內容
export function safeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

const signingKey = (env) => `${env.SESSION_SECRET}|${env.PORTFOLIO_PASSWORD}`;

export async function makeToken(env, now = Date.now()) {
  const exp = now + SESSION_DAYS * 86400_000;
  return `${exp}.${await hmacHex(signingKey(env), `pf:${exp}`)}`;
}

export async function validToken(env, token, now = Date.now()) {
  if (!token) return false;
  const [exp, sig] = token.split(".");
  if (!exp || !sig || !(Number(exp) > now)) return false;
  return safeEqual(sig, await hmacHex(signingKey(env), `pf:${exp}`));
}

// 兩邊都先 HMAC 成固定長度再比，密碼長度也不會從時間洩漏
export async function passwordMatches(env, password) {
  const [a, b] = await Promise.all([
    hmacHex(env.SESSION_SECRET, `pw:${password}`),
    hmacHex(env.SESSION_SECRET, `pw:${env.PORTFOLIO_PASSWORD}`),
  ]);
  return safeEqual(a, b);
}

export function getCookie(request, name) {
  for (const part of (request.headers.get("Cookie") || "").split(/;\s*/)) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i) === name) return decodeURIComponent(part.slice(i + 1));
  }
  return null;
}
