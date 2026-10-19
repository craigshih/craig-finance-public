// 驗證 Cloudflare Access 的登入憑證（Cf-Access-Jwt-Assertion），取得使用者 email。
// Access 已經擋在整個網站前面，這裡再驗一次簽章，確保 email 不是被偽造的 header。

const enc = new TextEncoder();
let certCache = { keys: null, at: 0 };

function b64urlToBytes(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  s += "=".repeat((4 - (s.length % 4)) % 4);
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}

const b64urlJson = (s) => JSON.parse(new TextDecoder().decode(b64urlToBytes(s)));

async function accessKeys(team, refresh = false) {
  if (!refresh && certCache.keys && Date.now() - certCache.at < 3600_000) return certCache.keys;
  const res = await fetch(`https://${team}/cdn-cgi/access/certs`);
  if (!res.ok) throw new Error(`Access certs ${res.status}`);
  certCache = { keys: (await res.json()).keys, at: Date.now() };
  return certCache.keys;
}

export async function accessEmail(request, env) {
  // 只給 CI 冒煙測試用：wrangler pages dev 跑在 localhost，前面沒有 Access
  const host = new URL(request.url).hostname;
  if (env.ACCESS_DEV_EMAIL && (host === "localhost" || host === "127.0.0.1")) return env.ACCESS_DEV_EMAIL;

  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token || !env.ACCESS_TEAM_DOMAIN || !env.ACCESS_AUD) return null;
  const [h, p, s] = token.split(".");
  if (!h || !p || !s) return null;

  let header, payload;
  try {
    header = b64urlJson(h);
    payload = b64urlJson(p);
  } catch {
    return null;
  }
  if (header.alg !== "RS256") return null;

  let jwk = (await accessKeys(env.ACCESS_TEAM_DOMAIN)).find((k) => k.kid === header.kid);
  if (!jwk) jwk = (await accessKeys(env.ACCESS_TEAM_DOMAIN, true)).find((k) => k.kid === header.kid); // 金鑰輪替
  if (!jwk) return null;

  const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  const ok = await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64urlToBytes(s), enc.encode(`${h}.${p}`));
  if (!ok) return null;

  const aud = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!aud.includes(env.ACCESS_AUD)) return null;
  if (!payload.exp || payload.exp * 1000 < Date.now()) return null;
  if (payload.iss !== `https://${env.ACCESS_TEAM_DOMAIN}`) return null;
  return typeof payload.email === "string" ? payload.email.toLowerCase() : null;
}
