// AI 投資顧問頁的前端。數字卡片一律顯示伺服器回傳的原始資料（不是 AI 寫的），AI 的文字另外呈現。
(() => {
  const $ = (sel) => document.querySelector(sel);
  const APP = document.querySelector("#adv-app");
  const API = APP?.dataset.api || "/portfolio/api/advisor";
  const HIST_KEY = APP?.dataset.hist || "advisor-history-v1";
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const k of kids.flat()) if (k != null && k !== false) n.append(k instanceof Node ? k : document.createTextNode(String(k)));
    return n;
  };
  const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toLocaleString("zh-TW", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const pctS = (x, d = 1) => (x == null ? "—" : (x > 0 ? "+" : "") + fmt(x, d) + "%");
  const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
  const lots = (x) => (x == null ? "—" : (x > 0 ? "+" : "") + Number(x).toLocaleString("zh-TW") + " 張");
  const STANCE = { 偏正面: "bull", 中性: "flat", 偏保守: "bear", 資料不足: "flat" };
  const stanceChip = (s) => el("span", { class: `stance ${STANCE[s] || "flat"}` }, s || "中性");

  const logo = (code, name, market) => {
    const base = "https://financialmodelingprep.com/image-stock/";
    const urls = market === "上櫃" ? [`${base}${code}.TWO.png`] : [`${base}${code}.TW.png`, `${base}${code}.TWO.png`];
    const hue = [...code].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
    const wrap = el("span", { class: "logo", style: `--h:${hue}` }, el("b", {}, (name || code)[0]));
    const img = el("img", { src: urls[0], alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
    let i = 0;
    img.addEventListener("error", () => { i += 1; if (urls[i]) img.src = urls[i]; else img.remove(); });
    wrap.append(img);
    return wrap;
  };

  const spark = (values) => {
    if (!values || values.length < 2) return null;
    const w = 160, h = 44, lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 3 - ((v - lo) / span) * (h - 6)}`).join(" ");
    const up = values[values.length - 1] >= values[0];
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("class", `spark ${up ? "pos" : ""}`);
    svg.innerHTML = `<polyline fill="none" stroke="currentColor" stroke-width="1.6" points="${pts}"/>`;
    return svg;
  };

  // 一格數據：標籤、數值、補充
  const cell = (label, value, foot, tone) => el("div", { class: "adv-cell" },
    el("small", {}, label), el("b", { class: tone || "" }, value), foot ? el("i", {}, foot) : null);

  function stockCard(s, view) {
    const r = s.risk || {}, b = s.backtest, f = s.flows, v = s.valuation || {}, rev = s.revenue, m = s.margins, mg = s.margin, p = s.ptt, fac = s.factors;
    const groups = [];
    groups.push(["籌碼", [
      f ? cell(`外資 ${f.days === 5 ? "5 日" : "當日"}`, lots(f.foreign_lots), f.date, cls(f.foreign_lots)) : cell("外資", "—", "沒有資料"),
      f ? cell(`投信 ${f.days === 5 ? "5 日" : "當日"}`, lots(f.trust_lots), f.buy_days != null ? `外資+投信買超 ${f.buy_days}/5 天` : "上櫃只有當日", cls(f.trust_lots)) : null,
      mg ? cell("融資增減", lots(mg.change), `使用率 ${fmt(mg.usage)}%`, cls(mg.change)) : null,
    ]]);
    groups.push(["財報", [
      rev ? cell(`月營收年增（${rev.month}）`, pctS(rev.yoy), `累計 ${pctS(rev.ytd_yoy)}`, cls(rev.yoy)) : cell("月營收", "—"),
      m ? cell(`毛利率（${m.quarter}）`, `${fmt(m.gross)}%`, `營益率 ${fmt(m.operating)}%・淨利率 ${fmt(m.net)}%`) : null,
      cell("本益比", v.pe ? fmt(v.pe) : "—", `淨值比 ${fmt(v.pb, 2)}・殖利率 ${fmt(v.yield, 2)}%`),
      v.roe_est != null ? cell("ROE（估）", `${fmt(v.roe_est)}%`, "≈ 淨值比 ÷ 本益比") : null,
    ]]);
    groups.push(["輿情", [
      p ? cell("PTT 股板提及", `${p.mentions} 篇`, `最近 ${p.sample} 篇標題`) : cell("PTT 股板", "暫時抓不到", "今天沒有取得資料"),
      p ? cell("[標的] 文", `多 ${p.target_bull}・空 ${p.target_bear}`, "多空篇數") : null,
      cell("今日新聞", `${(s.news || []).length} 則`, "鉅亨網標題點名"),
    ]]);
    const w = s.held?.weight_pct;
    groups.push(["風控（陣營 A）", s.risk ? [
      cell("最大回撤 1 年", `${fmt(r.mdd_1y)}%`, `3 年 ${fmt(r.mdd_3y)}%`, "neg"),
      cell("單日 VaR 95%", `${fmt(r.var95_1d, 2)}%`, `年化波動 ${fmt(r.vol_1y)}%`),
      r.stress ? cell("壓力測試", `${pctS(r.stress.stock)}`, `大盤 ${pctS(r.stress.market)}（${r.stress.from}～${r.stress.to}）`, cls(r.stress.stock)) : null,
      cell("Beta（對 0050）", r.beta != null ? fmt(r.beta, 2) : "—", `距 52 週高 ${pctS(r.from_52w_high)}`),
      w != null ? cell("我的部位", `${fmt(w)}%`, w > 15 ? "超過 15% 上限" : "在 15% 上限內", w > 15 ? "pos" : "") : null,
    ] : [cell("價格風險", "明天補上", "這檔還不在每日計算範圍，已自動加入")]]);
    groups.push(["回測（陣營 B）", b ? [
      cell("規則年化報酬", pctS(b.strategy_cagr), `買進持有 ${pctS(b.hold_cagr)}`, cls(b.strategy_cagr)),
      cell("規則最大回撤", `${fmt(b.strategy_mdd)}%`, `買進持有 ${fmt(b.hold_mdd)}%`),
      cell("勝率", b.win_rate != null ? `${fmt(b.win_rate, 0)}%` : "—", `${b.trades} 筆・平均 ${pctS(b.avg_trade)}`),
      cell("夏普比率 1 年", r.sharpe_1y != null ? fmt(r.sharpe_1y, 2) : "—", `目前訊號：${b.holding_now ? "持有" : "空手"}`),
      fac?.composite != null ? cell("多因子百分位", `${fac.composite}`, `營收 ${fac.revenue_yoy ?? "—"}・低本益比 ${fac.low_pe ?? "—"}・投信 ${fac.trust_buy ?? "—"}`) : null,
    ] : [cell("回測", "明天補上", "這檔還不在每日計算範圍")]]);

    const stanceInfo = view?.stocks?.find((x) => x.code === s.code);
    return el("article", { class: "adv-card" },
      el("header", { class: "adv-card-head" },
        logo(s.code, s.name, s.market),
        el("div", { class: "adv-title" }, el("h3", {}, s.name, " ", el("small", {}, s.code)),
          el("small", {}, [s.market, s.industry].filter(Boolean).join("・"))),
        el("div", { class: "adv-price" }, el("b", {}, fmt(r.price ?? s.close, 2)),
          r.ret_1y != null ? el("small", { class: cls(r.ret_1y) }, `近一年 ${pctS(r.ret_1y)}`) : null),
        spark(r.spark)),
      stanceInfo ? el("p", { class: "adv-stance" }, stanceChip(stanceInfo.stance), stanceInfo.summary) : null,
      ...groups.map(([title, cells]) => el("div", { class: "adv-group" }, el("h4", {}, title), el("div", { class: "adv-cells" }, cells.filter(Boolean)))),
      s.weekly ? el("p", { class: "adv-weekly" }, el("span", { class: "pill" }, `每週研究 ${s.weekly.date}`),
        ` ${s.weekly.style}股篩選通過 ${s.weekly.passed}/${s.weekly.total} 項`,
        s.weekly.failed.length ? el("small", {}, `　未過：${s.weekly.failed.join("；")}`) : null) : null,
      b ? el("p", { class: "adv-rule" }, `回測規則：${b.rule}（${b.period}，已扣手續費與證交稅；樣本內結果，不代表未來）`) : null);
  }

  function campCard(kind, c) {
    if (!c) return null;
    const meta = kind === "a"
      ? ["shield", "陣營 A・風控管理", "防守：先保住本金"]
      : ["rocket", "陣營 B・量化回測", "進攻：追求超額報酬"];
    return el("div", { class: `adv-camp ${kind}` },
      el("div", { class: "adv-camp-head" }, el("img", { class: "ui-ico md", src: `/ui/${meta[0]}.svg`, alt: "" }),
        el("div", {}, el("b", {}, meta[1]), el("small", {}, meta[2])), stanceChip(c.stance)),
      el("p", {}, c.argument),
      c.points.length ? el("ul", {}, c.points.map((p) => el("li", { class: p.startsWith("（系統註記）") ? "sysnote" : null }, p))) : null);
  }

  function sources(stocks) {
    const items = [];
    for (const s of stocks) {
      for (const n of s.news || []) items.push(el("li", {}, el("span", { class: "pill" }, "新聞"), el("a", { href: n.url, target: "_blank", rel: "noopener" }, n.title), el("small", {}, ` 鉅亨網`)));
      for (const x of s.supply || []) {
        const label = `${s.name} ${x.relation} ${x.leader}：${x.note}`;
        items.push(el("li", {}, el("span", { class: "pill" }, "供應鏈"), x.source.url ? el("a", { href: x.source.url, target: "_blank", rel: "noopener" }, label) : label,
          el("small", {}, ` ${x.source.publisher}${x.source.date ? " " + x.source.date : ""}`)));
      }
      for (const t of (s.ptt?.titles || []).slice(0, 3)) items.push(el("li", {}, el("span", { class: "pill" }, "PTT"), t));
    }
    return items.length ? el("section", { class: "sec" }, el("div", { class: "sec-head" }, el("h2", {}, "資料出處"), el("span", { class: "sec-note" }, "AI 只看得到這些")),
      el("ul", { class: "feed adv-src" }, items)) : null;
  }

  function render(res, q) {
    const a = res.answer;
    const out = $("#adv-out");
    out.replaceChildren();
    const nameOf = Object.fromEntries(res.stocks.map((s) => [s.code, s.name]));
    out.append(el("section", { class: "sec adv-answer" },
      el("p", { class: "adv-q" }, "你問：", q),
      el("h2", { class: "adv-headline" }, a.headline),
      a.mode === "coach" && a.coach ? el("div", { class: "adv-coach" }, el("span", { class: "pill" }, "AI 教練"), el("p", {}, a.coach)) : null));

    if (res.stocks.length) {
      out.append(el("section", { class: "sec" }, el("div", { class: "sec-head" }, el("h2", {}, res.stocks.length > 1 ? "並排比較" : "數據"),
        el("span", { class: "sec-note" }, `原始資料・${res.data_date?.slice(0, 16).replace("T", " ")}`)),
        el("div", { class: `adv-cards n${res.stocks.length}` }, res.stocks.map((s) => stockCard(s, a)))));
    }
    if (a.risk_camp || a.quant_camp) {
      out.append(el("section", { class: "sec" }, el("div", { class: "sec-head" }, el("h2", {}, "核心辯論"), el("span", { class: "sec-note" }, "風控 vs 回測")),
        el("div", { class: "adv-debate" }, campCard("a", a.risk_camp), el("div", { class: "adv-vs" }, "VS"), campCard("b", a.quant_camp))));
    }
    if (a.synthesis) {
      const sy = a.synthesis;
      out.append(el("section", { class: "sec" }, el("div", { class: "sec-head" }, el("h2", {}, "AI 雙軌融合建言"), el("span", { class: "sec-note" }, "以風險調整後報酬為核心")),
        el("div", { class: "adv-synth" },
          el("p", { class: "adv-concl" }, sy.conclusion),
          sy.ranking.length > 1 ? el("ol", { class: "adv-rank" }, sy.ranking.map((r) => el("li", {}, el("b", {}, `${nameOf[r.code] || r.code}`), " ", r.reason))) : null,
          sy.position_note ? el("p", { class: "adv-pos" }, "部位提醒：", sy.position_note) : null,
          sy.conditions.length ? el("div", {}, el("small", {}, "什麼情況下這個看法會改變"), el("ul", {}, sy.conditions.map((c) => el("li", {}, c)))) : null)));
    }
    if (res.unverified?.length) {
      out.append(el("p", { class: "adv-warn" }, `⚠︎ AI 的回答裡有 ${res.unverified.length} 個數字在資料中找不到對應：${res.unverified.join("、")}。請以上方的原始數據為準。`));
    }
    if (res.missing_metrics?.length) {
      out.append(el("p", { class: "adv-warn soft" }, `${res.missing_metrics.map((c) => nameOf[c] || c).join("、")} 還沒有風控與回測數據，已加入每日計算，明天起會有。`));
    }
    const src = sources(res.stocks);
    if (src) out.append(src);
    if (a.follow_ups.length) {
      out.append(el("div", { class: "adv-sugg follow" }, el("small", {}, "接著問："), a.follow_ups.map((f) => el("button", { type: "button", class: "chip", "data-q": f }, f))));
    }
    out.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------- 歷史（只存在這台裝置） ----------
  const loadHist = () => { try { return JSON.parse(localStorage.getItem(HIST_KEY)) || []; } catch { return []; } };
  const saveHist = (h) => { try { localStorage.setItem(HIST_KEY, JSON.stringify(h.slice(0, 12))); } catch { /* 無痕模式 */ } };
  function drawHist() {
    const h = loadHist();
    $("#adv-hist-sec").hidden = !h.length;
    $("#adv-hist").replaceChildren(...h.map((x, i) => el("li", {},
      el("button", { type: "button", class: "linklike", onclick: () => render(x.res, x.q) }, x.q),
      el("small", {}, ` ${x.res.answer.headline}`))));
  }

  // ---------- 送出 ----------
  let busy = false, timer = null;
  function pipe(step) {
    const p = $("#adv-pipe");
    p.dataset.step = step;
    [...p.children].forEach((c, i) => c.classList.toggle("on", i < step));
  }
  async function ask(q) {
    if (busy || !q.trim()) return;
    busy = true;
    $("#adv-send").disabled = true;
    $("#adv-send").textContent = "分析中…";
    $("#adv-out").replaceChildren(el("p", { class: "adv-wait" }, "正在整理資料、讓兩派辯論…通常 10～30 秒"));
    let step = 1;
    pipe(step);
    timer = setInterval(() => pipe(Math.min(++step, 4)), 3500);
    try {
      const history = loadHist().slice(0, 2).map((x) => ({ q: x.q, headline: x.res.answer.headline })).reverse();
      const r = await fetch(API, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, history }),
      });
      if (r.status === 401) { location.reload(); return; }
      const res = await r.json();
      if (!r.ok) throw new Error(res.error || "顧問暫時無法回答");
      pipe(5);
      render(res, q);
      saveHist([{ q, res, at: Date.now() }, ...loadHist().filter((x) => x.q !== q)]);
      drawHist();
    } catch (exc) {
      $("#adv-out").replaceChildren(el("p", { class: "adv-warn" }, exc.message));
      pipe(0);
    } finally {
      clearInterval(timer);
      busy = false;
      $("#adv-send").disabled = false;
      $("#adv-send").textContent = "問顧問";
    }
  }

  $("#adv-form").addEventListener("submit", (ev) => { ev.preventDefault(); ask($("#adv-q").value); });
  $("#adv-q").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); ask($("#adv-q").value); }
  });
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-q]");
    if (!b) return;
    $("#adv-q").value = b.dataset.q;
    ask(b.dataset.q);
  });
  $("#adv-clear").addEventListener("click", () => { saveHist([]); drawHist(); });
  drawHist();
  // 從「幫我找股票」點「問顧問這檔」過來：先把問題填好，按送出才問（不自動用掉額度）
  const pre = new URLSearchParams(location.search).get("q");
  if (pre) { $("#adv-q").value = pre.slice(0, 300); $("#adv-q").focus(); }
})();
