// node --test tests/：交易成本、報價解析、密碼 cookie、Access 憑證驗證。
import assert from "node:assert/strict";
import { test } from "node:test";

import { accessEmail } from "../functions/_lib/auth.js";
import { orderCost, parseQuotes, taxRate, validateOrder, valuate } from "../functions/_lib/market.js";
import { makeToken, passwordMatches, validToken } from "../functions/_lib/session.js";

test("證交稅率：股票 0.3%、ETF 0.1%、債券 ETF 免徵", () => {
  assert.equal(taxRate("2330"), 0.003);
  assert.equal(taxRate("0050"), 0.001);
  assert.equal(taxRate("00679B"), 0);
});

test("整股手續費最低 20 元、零股最低 1 元、無條件捨去", () => {
  assert.deepEqual(orderCost({ code: "0050", side: "buy", price: 10, shares: 1000 }), { amount: 10000, fee: 20, tax: 0, total: 10020 });
  assert.deepEqual(orderCost({ code: "0050", side: "buy", price: 10, shares: 10 }), { amount: 100, fee: 1, tax: 0, total: 101 });
  // 2330 一張 @ 2500：金額 2,500,000，手續費 3562.5 → 3562
  assert.equal(orderCost({ code: "2330", side: "buy", price: 2500, shares: 1000 }).fee, 3562);
});

test("賣出扣手續費與證交稅", () => {
  const c = orderCost({ code: "2330", side: "sell", price: 2500, shares: 1000 });
  assert.equal(c.tax, 7500);
  assert.equal(c.total, 2_500_000 - 3562 - 7500);
});

test("下單參數檢查", () => {
  assert.deepEqual(validateOrder({ code: " 2330 ", side: "buy", shares: 5 }), { code: "2330", side: "buy", shares: 5 });
  assert.throws(() => validateOrder({ code: "2330", side: "buy", shares: 1.5 }), /整數/);
  assert.throws(() => validateOrder({ code: "2330", side: "buy", shares: 0 }), /整數/);
  assert.throws(() => validateOrder({ code: "2330", side: "short", shares: 1 }), /買賣別/);
  assert.throws(() => validateOrder({ code: "<x>", side: "buy", shares: 1 }), /代號/);
});

test("解析證交所與櫃買中心報價（民國日期、跳過沒有成交的）", () => {
  const q = parseQuotes(
    [{ Code: "2330", Name: "台積電", ClosingPrice: "2,500.00", Date: "1151002" }, { Code: "9999", Name: "x", ClosingPrice: "", Date: "1151002" }],
    [{ SecuritiesCompanyCode: "6488", CompanyName: "環球晶", Close: "400.5", Date: "1151005" }, { SecuritiesCompanyCode: "1111", CompanyName: "y", Close: "----", Date: "1151005" }],
  );
  assert.deepEqual(Object.keys(q).sort(), ["2330", "6488"]);
  assert.equal(q["2330"].price, 2500);
  assert.equal(q["2330"].date, "2026-10-02");
  assert.equal(q["6488"].market, "上櫃");
});

test("持股估值；沒有報價的以成本計", () => {
  const { rows, value } = valuate(
    [{ code: "2330", name: "台積電", shares: 10, cost: 20000 }, { code: "0000", name: "下市", shares: 5, cost: 300 }],
    { "2330": { price: 2500 } },
  );
  assert.equal(value, 25000 + 300);
  assert.equal(rows[0].pl, 5000);
  assert.equal(rows[1].pl, 0);
});

const ENV = { PORTFOLIO_PASSWORD: "correct horse battery staple", SESSION_SECRET: "s".repeat(64) };

test("密碼比對", async () => {
  assert.equal(await passwordMatches(ENV, "correct horse battery staple"), true);
  assert.equal(await passwordMatches(ENV, "wrong"), false);
  assert.equal(await passwordMatches(ENV, ""), false);
});

test("登入 cookie：有效、過期、竄改、改密碼後失效", async () => {
  const token = await makeToken(ENV);
  assert.equal(await validToken(ENV, token), true);
  assert.equal(await validToken(ENV, token, Date.now() + 31 * 86400_000), false);
  const [exp, sig] = token.split(".");
  assert.equal(await validToken(ENV, `${Number(exp) + 1}.${sig}`), false);
  assert.equal(await validToken({ ...ENV, PORTFOLIO_PASSWORD: "new password" }, token), false);
  assert.equal(await validToken(ENV, null), false);
});

// ---- Access JWT：自己產生一組 RSA 金鑰，假裝成 Access 的憑證端點 ----
const b64url = (buf) => Buffer.from(buf).toString("base64url");

async function makeAccessFixture() {
  const { privateKey, publicKey } = await crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" }, true, ["sign", "verify"]);
  const jwk = { ...(await crypto.subtle.exportKey("jwk", publicKey)), kid: "k1" };
  const env = { ACCESS_TEAM_DOMAIN: "team.cloudflareaccess.com", ACCESS_AUD: "aud123" };
  const sign = async (payload, kid = "k1") => {
    const h = b64url(JSON.stringify({ alg: "RS256", kid }));
    const p = b64url(JSON.stringify(payload));
    const s = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", privateKey, new TextEncoder().encode(`${h}.${p}`));
    return `${h}.${p}.${b64url(s)}`;
  };
  globalThis.fetch = async (url) => {
    assert.equal(String(url), "https://team.cloudflareaccess.com/cdn-cgi/access/certs");
    return new Response(JSON.stringify({ keys: [jwk] }));
  };
  return { env, sign };
}

const req = (token, host = "craig-finance.pages.dev") =>
  new Request(`https://${host}/api/sim/me`, { headers: token ? { "Cf-Access-Jwt-Assertion": token } : {} });

test("Access 憑證：正確的才回 email", async () => {
  const { env, sign } = await makeAccessFixture();
  const good = { aud: ["aud123"], email: "Friend@Example.com", exp: Math.floor(Date.now() / 1000) + 600, iss: "https://team.cloudflareaccess.com" };
  assert.equal(await accessEmail(req(await sign(good)), env), "friend@example.com");
  assert.equal(await accessEmail(req(await sign({ ...good, aud: ["other"] })), env), null);
  assert.equal(await accessEmail(req(await sign({ ...good, exp: 1 })), env), null);
  assert.equal(await accessEmail(req(await sign({ ...good, iss: "https://evil.example" })), env), null);
  const tampered = (await sign(good)).split(".");
  tampered[1] = b64url(JSON.stringify({ ...good, email: "owner@example.com" }));
  assert.equal(await accessEmail(req(tampered.join(".")), env), null);
  assert.equal(await accessEmail(req(null), env), null);
});

test("測試用 email 只在 localhost 生效", async () => {
  const env = { ACCESS_DEV_EMAIL: "dev@example.com", ACCESS_TEAM_DOMAIN: "team.cloudflareaccess.com", ACCESS_AUD: "aud123" };
  assert.equal(await accessEmail(req(null, "localhost:8788"), env), "dev@example.com");
  assert.equal(await accessEmail(req(null), env), null);
});

test("解析鉅亨網 RSS：標題、縮圖、關鍵字、只留鉅亨網連結", async () => {
  const { parseRss } = await import("../functions/api/news.js");
  const xml = `<rss><channel>
<item><title><![CDATA[台積電 &amp; 英特爾]]></title><category>美股雷達</category><link>https://news.cnyes.com/news/id/1</link>
<description><![CDATA[<p>摘要內容</p>]]></description><pubDate>Mon, 05 Oct 2026 22:30:07 +0800</pubDate>
<media:thumbnail url="https://cimg.cnyes.cool/x.jpg" /><media:keywords><![CDATA[台積電,AI]]></media:keywords></item>
<item><title>外部連結</title><link>https://evil.example/</link><pubDate>Mon, 05 Oct 2026 22:30:07 +0800</pubDate></item>
</channel></rss>`;
  const items = parseRss(xml, "tw_stock");
  assert.equal(items.length, 1);
  assert.equal(items[0].title, "台積電 & 英特爾");
  assert.equal(items[0].thumb, "https://cimg.cnyes.cool/x.jpg");
  assert.deepEqual(items[0].keywords, ["台積電", "AI"]);
  assert.equal(items[0].summary, "摘要內容");
  assert.equal(items[0].time, "2026-10-05T14:30:07.000Z");
});
