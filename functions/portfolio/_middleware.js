// 投資頁的密碼鎖：/portfolio/ 底下所有內容（包含持股數字）都要先輸入密碼。
// 檢查在 Cloudflare 伺服器端進行，沒通過的人拿不到任何持股資料。

import { COOKIE, SESSION_DAYS, getCookie, makeToken, passwordMatches, validToken } from "../_lib/session.js";

const NO_STORE = "private, no-store";

function loginPage(message, status = 401, next = "/portfolio/") {
  const note = message ? `<p class="login-msg">${message}</p>` : "";
  const html = `<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>投資總覽 · Craig 財經站</title>
<link rel="stylesheet" href="/style.css"></head>
<body>
<header class="top"><div class="wrap"><a class="brand" href="/"><span class="mark">C</span><span class="brand-text">Craig 財經站</span></a>
<nav><a href="/">總覽</a><a href="/market/">台股</a><a href="/us/">美股</a><a href="/news/">即時快報</a><a href="/daily/">每日總經</a><a href="/weekly/">每週研究</a><a href="/supply/">供應鏈</a><a href="/whales/">大佬持股</a><a href="/sim/">模擬交易</a><a href="/robot/">專屬投資顧問</a><a class="on" href="/portfolio/">投資</a></nav></div></header>
<section class="hero"><div class="wrap"><div class="kicker">投資總覽</div><h1>這一頁需要密碼</h1>
<p class="hero-sub">持股與損益只給站長本人看。</p></div></section>
<main class="wrap"><form class="login" method="post" action="/portfolio/__login">
<label for="pw">密碼</label>
<input id="pw" name="password" type="password" autocomplete="current-password" required autofocus>
<input type="hidden" name="next" value="${next.replace(/[^\w\-/]/g, "")}">
<button type="submit">進入</button>${note}</form></main>
</body></html>`;
  return new Response(html, { status, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": NO_STORE } });
}

export async function onRequest({ request, env, next }) {
  const { pathname } = new URL(request.url);

  // 沒設定密碼時一律擋下，不會因為設定漏掉而公開
  if (!env.PORTFOLIO_PASSWORD || !env.SESSION_SECRET) return loginPage("投資頁的密碼還沒設定，暫時無法查看。", 503);

  const cookieAttrs = "Path=/portfolio; HttpOnly; Secure; SameSite=Lax";

  if (pathname === "/portfolio/__logout") {
    return new Response(null, { status: 303, headers: { Location: "/", "Set-Cookie": `${COOKIE}=; ${cookieAttrs}; Max-Age=0` } });
  }

  if (pathname === "/portfolio/__login") {
    if (request.method !== "POST") return Response.redirect(new URL("/portfolio/", request.url), 303);
    const form = await request.formData();
    if (await passwordMatches(env, String(form.get("password") || ""))) {
      const token = await makeToken(env);
      const back = String(form.get("next") || "");
      const target = /^\/portfolio\/[\w\-/]*$/.test(back) && !back.includes("__") ? back : "/portfolio/";
      return new Response(null, {
        status: 303,
        headers: { Location: target, "Cache-Control": NO_STORE,
                   "Set-Cookie": `${COOKIE}=${token}; ${cookieAttrs}; Max-Age=${SESSION_DAYS * 86400}` },
      });
    }
    await new Promise((r) => setTimeout(r, 1000)); // 拖慢猜密碼
    return loginPage("密碼不正確", 401, String(form.get("next") || "/portfolio/"));
  }

  if (await validToken(env, getCookie(request, COOKIE))) {
    const res = await next();
    const out = new Response(res.body, res);
    out.headers.set("Cache-Control", NO_STORE);
    return out;
  }
  if (pathname.startsWith("/portfolio/api/")) return Response.json({ error: "請重新輸入密碼" }, { status: 401 });
  return loginPage("", 401, pathname);
}
