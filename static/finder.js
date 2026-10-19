// 選股機器人頁的前端：數字卡片一律顯示伺服器回傳的原始資料，AI 寫的理由另外呈現。
(() => {
  const $ = (sel) => document.querySelector(sel);
  const APP = $("#fd-app");
  const API = APP.dataset.api;
  const ADVISOR = APP.dataset.advisor || "../";
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const c of kids.flat()) if (c != null && c !== false) n.append(c.nodeType ? c : String(c));
    return n;
  };
  const fmt = (x, d = 1) => (x == null ? "—" : Number(x).toLocaleString("zh-TW", { maximumFractionDigits: d, minimumFractionDigits: d }));
  const pct = (x) => (x == null ? "—" : `${x > 0 ? "+" : ""}${fmt(x)}%`);
  const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
  const cap = (yi) => (yi == null ? "—" : yi >= 10000 ? `${fmt(yi / 10000, 2)} 兆` : `${fmt(yi, 0)} 億`);

  const SPEC_LABEL = { leaders: "龍頭（產業市值前三）", dip: "近期跌深", dividend: "重視配息", value: "本益比低", growth: "營收成長", low_risk: "波動小", etf: "ETF" };
  function specChips(spec) {
    const chips = [...spec.industries, ...spec.themes, ...Object.keys(SPEC_LABEL).filter((k) => spec[k]).map((k) => SPEC_LABEL[k])];
    if (spec.names?.length) chips.push(`你提到：${spec.names.join("、")}`);
    return el("div", { class: "fd-spec" }, el("small", {}, "我理解的條件："),
      ...(chips.length ? chips : ["全市場，不限產業"]).map((c) => el("span", { class: "chip static" }, c)));
  }

  function card(c, a) {
    const cell = (k, v, cl = "") => el("div", {}, el("small", {}, k), el("b", { class: cl }, v));
    const ask = `${c.name}（${c.code}）現在值得研究嗎？`;
    return el("article", { class: "fd-card" },
      el("header", {},
        el("div", {}, el("b", {}, c.name), el("small", {}, ` ${c.code}・${c.market}・${c.industry || ""}`)),
        el("div", { class: "fd-badges" },
          c.rank && c.rank <= 3 ? el("span", { class: "fd-badge" }, `產業市值第 ${c.rank}`) : "",
          c.held ? el("span", { class: "fd-badge held" }, "你已持有") : "")),
      el("div", { class: "fd-cells" },
        cell("收盤", fmt(c.close, 2)), cell("近 5 日", pct(c.chg_5d), cls(c.chg_5d)), cell("近 20 日", pct(c.chg_20d), cls(c.chg_20d)),
        cell("本益比", fmt(c.pe)), cell("殖利率", c.yield == null ? "—" : `${fmt(c.yield, 2)}%`),
        cell("月營收年增", pct(c.rev_yoy), cls(c.rev_yoy)), cell("毛利率", c.gross == null ? "—" : `${fmt(c.gross)}%`), cell("市值", cap(c.mcap_yi))),
      c.reasons?.length ? el("div", { class: "fd-reasons" }, ...c.reasons.map((r) => el("span", { class: "chip static" }, r))) : "",
      a?.why ? el("p", { class: "fd-why" }, a.why) : "",
      a?.watch ? el("p", { class: "fd-watch" }, el("b", {}, "留意："), a.watch) : "",
      el("a", { class: "btn ghost fd-ask", href: `${ADVISOR}?q=${encodeURIComponent(ask)}` }, "問顧問這檔 →"));
  }

  async function find(q) {
    q = String(q || "").trim();
    if (!q) return;
    const out = $("#fd-out");
    const btn = $("#fd-send");
    btn.disabled = true;
    out.replaceChildren(el("div", { class: "adv-wait" }, "理解你的條件、從全市場挑選中…（約 20 秒）"));
    try {
      const res = await fetch(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      const d = await res.json().catch(() => ({ error: "伺服器沒有回應" }));
      if (!res.ok) throw new Error(d.error || `錯誤 ${res.status}`);
      const byCode = Object.fromEntries((d.picks || []).map((p) => [p.code, p]));
      out.replaceChildren(el("section", { class: "sec fd-result" },
        el("p", { class: "adv-q" }, "你想找：", q),
        d.spec ? specChips(d.spec) : "",
        d.intro ? el("p", { class: "fd-intro" }, d.intro) : "",
        d.cards?.length ? el("div", { class: "fd-grid" }, ...d.cards.map((c) => card(c, byCode[c.code]))) : "",
        d.cautions?.length ? el("div", { class: "fd-caution" }, el("b", {}, "整體提醒"), el("ul", {}, ...d.cautions.map((x) => el("li", {}, x)))) : "",
        d.unverified?.length ? el("p", { class: "adv-warn" }, `⚠️ AI 文字裡有 ${d.unverified.length} 個數字在資料裡找不到（${d.unverified.slice(0, 5).join("、")}），請以卡片上的原始數字為準。`) : "",
        d.data_date ? el("p", { class: "adv-meta" }, `資料日期 ${d.data_date.slice(0, 10)}・卡片數字來自證交所、櫃買中心每日資料`) : ""));
      out.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      out.replaceChildren(el("p", { class: "soon" }, e.message));
    } finally {
      btn.disabled = false;
    }
  }

  $("#fd-form").addEventListener("submit", (ev) => { ev.preventDefault(); find($("#fd-q").value); });
  $("#fd-q").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); find($("#fd-q").value); }
  });
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-fq]");
    if (!b) return;
    $("#fd-q").value = b.dataset.fq;
    find(b.dataset.fq);
  });
})();
