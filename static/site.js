// 全站共用的動畫：捲動進場、數字跳動、長條展開、即時新聞跑馬燈與快報頁。
// 使用者在系統設定「減少動態效果」時，全部改成直接顯示。
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.documentElement.classList.add("js");
  // 顯示的時間一律往下取到 5 分鐘整、不顯示秒（站長偏好）
  window.hm5 = (t) => { const d = new Date(new Date(t).getTime() + 8 * 3600_000); const m = d.getUTCMinutes() - (d.getUTCMinutes() % 5);
    return `${String(d.getUTCHours()).padStart(2, "0")}:${String(m).padStart(2, "0")}`; };

  // ---- 手機導覽列：把目前所在的分頁捲到看得見的位置（只捲導覽列本身，不動整頁）----
  const nav = document.querySelector(".top nav"), cur = nav?.querySelector("a.on");
  if (nav && cur && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = cur.getBoundingClientRect().left - nav.getBoundingClientRect().left - (nav.clientWidth - cur.offsetWidth) / 2;

  // ---- 捲動進場：.sec、卡片、表格列依序淡入 ----
  const targets = document.querySelectorAll(".sec, .stat, .pick, .news, .co, .date-card, .locked, .persona, .obs, .digest-hero li, .bubble, .inv, .rcard");
  targets.forEach((el, i) => {
    el.classList.add("reveal");
    el.style.setProperty("--d", `${(i % 6) * 60}ms`);
  });
  if (reduce || !("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("in"));
  } else {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }, { rootMargin: "0px 0px -8% 0px" });
    targets.forEach((el) => {
      // 一開始就在畫面裡的直接進場，不等捲動事件
      if (el.getBoundingClientRect().top < innerHeight) requestAnimationFrame(() => el.classList.add("in"));
      else io.observe(el);
    });
    // 保險：不管什麼原因沒觸發（背景分頁、舊瀏覽器），2.5 秒後全部顯示，內容絕不會一直是透明的
    setTimeout(() => targets.forEach((el) => el.classList.add("in")), 2500);
  }

  // ---- 數字跳動：data-count 的元素從 0 數到目標值（只動第一個文字節點，單位與符號保留）----
  const firstText = (node) => {
    while (node && node.nodeType === 1) node = node.firstChild;
    return node && node.nodeType === 3 ? node : null;
  };
  const countUp = (el) => {
    const node = firstText(el);
    const m = node && node.textContent.match(/^(\s*[+\-]?)([\d,]+(?:\.\d+)?)(.*)$/s);
    if (!m) return;
    const [, sign, digits, rest] = m;
    const final = node.textContent;
    setTimeout(() => { node.textContent = final; }, 2500); // 保險：背景分頁動畫被暫停時，也一定回到正確數字
    const target = Number(digits.replace(/,/g, ""));
    const decimals = (digits.split(".")[1] || "").length;
    const start = performance.now();
    const step = (t) => {
      const p = Math.min(1, (t - start) / 900);
      const v = target * (1 - Math.pow(1 - p, 3));
      node.textContent = sign + v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + rest;
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  if (!reduce && "IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { countUp(e.target); io.unobserve(e.target); }
    });
    document.querySelectorAll("[data-count]").forEach((el) => io.observe(el));
  }

  // ---- 即時快報：首頁跑馬燈與 /news/ 頁 ----
  const ago = (iso) => {
    const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
    if (m < 1) return "剛剛";
    if (m < 60) return `${m} 分鐘前`;
    const h = Math.round(m / 60);
    return h < 24 ? `${h} 小時前` : new Date(iso).toLocaleDateString("zh-TW", { month: "numeric", day: "numeric" });
  };
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const k of kids) if (k != null && k !== "") n.append(k instanceof Node ? k : document.createTextNode(k));
    return n;
  };
  // 太泛的關鍵字不當作產業標籤
  const GENERIC = new Set(["TOP", "headline", "台股", "美股", "國際股", "科技", "產業", "鉅亨速報", "Factset", "外資", "大盤",
    "加權指數", "台積電ADR", "股市", "新聞", "財經", "市場", "經濟", "投資", "盤勢", "個股", "櫃買", "觀察", "焦點",
    "市場預估", "EPS", "目標價", "盤中速報", "美股盤中", "鉅亨看世界", "美股雷達"]);

  // Q 版主題圖示（topics.js 由 build.py 依 icons.py 產生），取代畫質不穩的新聞縮圖
  const qicon = (text, title) => {
    const Q = window.QTOPICS;
    if (!Q) return null;
    const hit = Q.topics.find(([, , kws]) => kws.some((k) => text.includes(k))) || Q.topics[Q.topics.length - 1];
    const count = (ws) => ws.reduce((n, w) => n + (title.split(w).length - 1), 0);
    const box = el("div", { class: `qthumb t-${hit[0]}` });
    const neg = count(Q.neg), pos = count(Q.pos);
    box.innerHTML = Q.icons[hit[0]][neg > pos ? "sad" : pos > neg ? "happy" : "calm"];
    box.append(el("span", { class: "qtag" }, hit[1]));
    return box;
  };

  async function loadNews(cat = "all") {
    const res = await fetch(`/api/news?cat=${cat}`);
    if (!res.ok) throw new Error("新聞暫時讀不到");
    return res.json();
  }

  // 首頁跑馬燈
  const ticker = document.querySelector("#live-ticker");
  if (ticker) {
    const fill = async () => {
      try {
        const { items } = await loadNews("all");
        ticker.replaceChildren(...items.slice(0, 8).map((i) =>
          el("li", {}, el("span", { class: "pill" }, i.feed_label), el("a", { href: i.url, target: "_blank", rel: "noopener" }, i.title),
            el("span", { class: "time" }, ago(i.time)))));
      } catch (e) { ticker.replaceChildren(el("li", { class: "empty" }, e.message)); }
    };
    fill();
    setInterval(fill, 180_000);
  }

  // 快報頁
  const app = document.querySelector("#news-app");
  if (app) {
    let cat = "all", kw = null, data = null;
    const list = app.querySelector("#news-list"), chips = app.querySelector("#news-chips"), stamp = document.querySelector("#news-updated");
    const render = () => {
      const items = data.items.filter((i) => !kw || i.keywords.includes(kw));
      list.replaceChildren(...(items.length ? items.map((i, n) => {
        const fresh = Date.now() - new Date(i.time) < 30 * 60000;
        return el("a", { class: "nitem reveal in", href: i.url, target: "_blank", rel: "noopener", style: `--d:${Math.min(n, 10) * 40}ms` },
          qicon(`${i.title} ${i.keywords.join(" ")}`, i.title) || el("div", { class: "noimg" }, i.feed_label),
          el("div", { class: "nbody" },
            el("div", { class: "nmeta" }, el("span", { class: "pill" }, i.feed_label), i.category ? el("span", {}, i.category) : "",
              fresh ? el("span", { class: "new" }, "NEW") : "", el("span", { class: "time" }, ago(i.time))),
            el("h3", {}, i.title), el("p", {}, i.summary),
            el("div", { class: "kws" }, ...i.keywords.filter((k) => !GENERIC.has(k)).slice(0, 4).map((k) => el("span", {}, `#${k}`)))));
      }) : [el("p", { class: "empty" }, "這個分類目前沒有新聞")]));
    };
    const renderChips = () => {
      const count = {};
      for (const i of data.items) for (const k of i.keywords) if (!GENERIC.has(k) && k.length <= 8) count[k] = (count[k] || 0) + 1;
      const top = Object.entries(count).filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]).slice(0, 14);
      chips.replaceChildren(
        el("button", { class: kw ? "" : "on", onclick: () => { kw = null; renderChips(); render(); } }, "全部"),
        ...top.map(([k, n]) => el("button", { class: kw === k ? "on" : "", onclick: () => { kw = k; renderChips(); render(); } },
          k, el("small", {}, String(n)))));
    };
    const refresh = async () => {
      try {
        data = await loadNews(cat);
        stamp.textContent = `更新於 ${hm5(data.updated)}・每 3 分鐘自動更新`;
        if (kw && !data.items.some((i) => i.keywords.includes(kw))) kw = null;
        renderChips();
        render();
      } catch (e) { list.replaceChildren(el("p", { class: "empty" }, e.message)); }
    };
    for (const b of app.querySelectorAll("#news-tabs button")) b.addEventListener("click", () => {
      cat = b.dataset.cat;
      kw = null;
      app.querySelectorAll("#news-tabs button").forEach((x) => x.classList.toggle("on", x === b));
      refresh();
    });
    refresh();
    setInterval(refresh, 180_000);
  }

  // ---- 即時報價：頂部跑馬燈、市場頁指數、投資頁持股（每次開啟就抓最新，之後每 60 秒更新）----
  const fmtN = (n, d = 2) => Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  const tone = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
  const flash = (node, dir) => {
    if (!node || reduce) return;
    node.classList.remove("flash-up", "flash-down");
    void node.offsetWidth;
    node.classList.add(dir > 0 ? "flash-up" : "flash-down");
  };
  const setText = (node, text, cls) => {
    if (!node) return;
    const changed = node.textContent !== text;
    node.textContent = text;
    if (cls !== undefined) node.classList.remove("pos", "neg"), cls && node.classList.add(cls);
    return changed;
  };
  const strip = document.querySelector("#tk");
  const twCodes = [...new Set([...document.querySelectorAll("[data-live-tw]")].map((n) => n.dataset.liveTw))];
  const usCodes = [...new Set([...document.querySelectorAll("[data-live-us]")].map((n) => n.dataset.liveUs))];
  const wantIdx = strip || document.querySelector("[data-live-idx]");
  const last = {};

  function paintStrip(idx) {
    const items = Object.entries(idx).map(([sym, q]) => el("span", { class: "tk-item", "data-sym": sym },
      el("b", {}, q.name), el("span", {}, fmtN(q.price, q.price > 1000 ? 0 : 2)),
      el("i", { class: tone(q.chg) }, `${q.chg > 0 ? "▲" : q.chg < 0 ? "▼" : "–"} ${Math.abs(q.pct).toFixed(2)}%`)));
    if (!items.length) return;
    const track = el("div", { class: "tk-track" }, ...items, ...items.map((n) => n.cloneNode(true)));
    track.style.setProperty("--dur", `${items.length * 5}s`);
    strip.replaceChildren(track);
  }

  async function live(first) {
    if ((!first && document.hidden) || (!wantIdx && !twCodes.length && !usCodes.length)) return;
    const qs = new URLSearchParams();
    if (wantIdx) qs.set("idx", "1");
    if (twCodes.length) qs.set("tw", twCodes.join(","));
    if (usCodes.length) qs.set("us", usCodes.join(","));
    let data;
    try {
      const res = await fetch(`/api/live?${qs}`);
      if (!res.ok) return;
      data = await res.json();
    } catch { return; }
    const idx = data.idx || {};
    if (strip) paintStrip(idx);
    for (const node of document.querySelectorAll("[data-live-idx]")) {
      const q = idx[node.dataset.liveIdx];
      if (!q) continue;
      const v = node.querySelector(".mk-idx-val");
      if (setText(v, fmtN(q.price))) flash(v, q.price - (last[node.dataset.liveIdx] ?? q.price));
      setText(node.querySelector(".mk-idx-chg"), `${q.chg > 0 ? "+" : ""}${fmtN(q.chg)}（${q.pct > 0 ? "+" : ""}${q.pct.toFixed(2)}%）`, tone(q.chg));
      last[node.dataset.liveIdx] = q.price;
    }
    let total = 0, base = 0, priced = 0;
    for (const node of document.querySelectorAll("[data-live-tw]")) {
      const q = (data.tw || {})[node.dataset.liveTw];
      if (!q) continue;
      priced += 1;
      const p = node.querySelector("[data-f=price]");
      if (setText(p, fmtN(q.price))) flash(p, q.chg);
      setText(node.querySelector("[data-f=pct]"), `${q.pct > 0 ? "+" : ""}${q.pct.toFixed(2)}%`, tone(q.chg));
      const shares = Number(node.dataset.shares || 0), cost = Number(node.dataset.cost || 0);
      if (shares) {
        const value = q.price * shares;
        total += value;
        base += Number(node.dataset.value || value);
        setText(node.querySelector("[data-f=value]"), fmtN(value, 0));
        if (cost) {
          setText(node.querySelector("[data-f=pl]"), `${value - cost > 0 ? "+" : ""}${fmtN(value - cost, 0)}`, tone(value - cost));
          setText(node.querySelector("[data-f=plpct]"), `${value > cost ? "+" : ""}${((value / cost - 1) * 100).toFixed(1)}%`, tone(value - cost));
        }
      }
    }
    for (const node of document.querySelectorAll("[data-live-us]")) {
      const q = (data.us || {})[node.dataset.liveUs];
      if (!q) continue;
      const p = node.querySelector("[data-f=price]");
      if (setText(p, `$${fmtN(q.price)}`)) flash(p, q.chg);
      setText(node.querySelector("[data-f=pct]"), `${q.pct > 0 ? "+" : ""}${q.pct.toFixed(2)}%`, tone(q.chg));
    }
    const pf = document.querySelector("#pf-live");
    if (pf && priced && total) {
      pf.hidden = false;
      pf.replaceChildren("盤中即時市值 ", el("b", {}, fmtN(total, 0)), el("span", { class: tone(total - base) }, `（較 Notion 收盤 ${total - base > 0 ? "+" : ""}${fmtN(total - base, 0)}）`));
    }
    document.querySelectorAll(".live-stamp").forEach((n) => { n.textContent = `即時 ${hm5(data.updated)}`; });
  }
  live(true);
  setInterval(live, 60_000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) live(); });

  // ---- 頁面載入進度條（紅→黃） ----
  if (!reduce) {
    const bar = el("div", { class: "loadbar" });
    document.body.append(bar);
    addEventListener("load", () => bar.classList.add("done"));
    setTimeout(() => bar.classList.add("done"), 2500);
  }

  // ---- 供應鏈地圖：切換龍頭、市場篩選 ----
  const supply = document.querySelector("#supply-app");
  if (supply) {
    // 手機上關係圖比螢幕寬，捲到正中間讓龍頭在畫面中央
    const center = (w) => { if (w) w.scrollLeft = (w.scrollWidth - w.clientWidth) / 2; };
    const pick = (code, scroll) => {
      supply.querySelectorAll(".lpanel[data-leader]").forEach((p) => {
        const on = p.dataset.leader === code;
        p.hidden = !on;
        if (on) {
          const svg = p.querySelector(".net"); svg.classList.remove("play"); void svg.getBBox(); svg.classList.add("play");
          center(p.querySelector(".netwrap"));
        }
      });
      supply.querySelectorAll("[data-pick]").forEach((b) => b.classList.toggle("on", b.dataset.pick === code));
      if (scroll) supply.querySelector(`.lpanel[data-leader="${CSS.escape(code)}"]`)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    };
    const tpick = (code) => {
      supply.querySelectorAll(".tpanel").forEach((p) => {
        const on = p.dataset.tw === code;
        p.hidden = !on;
        if (on) {
          const svg = p.querySelector(".net"); svg.classList.remove("play"); void svg.getBBox(); svg.classList.add("play");
          center(p.querySelector(".netwrap"));
        }
      });
      supply.querySelectorAll("[data-tpick]").forEach((b) => b.classList.toggle("on", b.dataset.tpick === code));
    };
    supply.addEventListener("click", (ev) => {
      const tb = ev.target.closest("[data-tpick]");
      if (tb) tpick(tb.dataset.tpick);
      const b = ev.target.closest("[data-pick]");
      if (b) pick(b.dataset.pick, !b.classList.contains("lchip"));
      const m = ev.target.closest("[data-market]");
      if (m) {
        supply.querySelectorAll("#mk-tabs button").forEach((x) => x.classList.toggle("on", x === m));
        supply.querySelectorAll(".lchip").forEach((c) => { c.hidden = m.dataset.market !== "全部" && c.dataset.mk !== m.dataset.market; });
      }
    });
    supply.querySelectorAll(".net").forEach((n) => n.classList.add("play"));
    supply.querySelectorAll(".lpanel:not([hidden]) .netwrap").forEach(center);
    // 從投資頁點過來時網址帶 #龍頭代號，直接打開那一家
    const want = decodeURIComponent(location.hash.slice(1));
    if (want && supply.querySelector(`.lpanel[data-leader="${CSS.escape(want)}"]`)) pick(want, true);
  }
})();

// ---- 術語小註解：標題、欄位名稱裡出現 glossary.js 的術語時，旁邊加一個小問號 ----
// 每個術語每頁只標第一次出現，避免畫面滿是問號；電腦滑過去就顯示，手機點了從下方滑出。
(() => {
  const G = window.GLOSS || [];
  if (!G.length) return;
  const names = [];
  G.forEach((g, i) => [g.t, ...g.a].forEach((n) => names.push([n, i])));
  names.sort((a, b) => b[0].length - a[0].length); // 長的先比：「融資餘額」不會被拆成「融資」
  const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(names.map(([n]) => (/^[A-Za-z]/.test(n) ? `(?<![A-Za-z])${esc(n)}(?![A-Za-z])` : esc(n))).join("|"));
  const index = Object.fromEntries(names);
  const SEL = ".sec-head h2, .stat-label, .br-tile > small, .br-tag, .thead > span, th, .mk-idx-top b, .pick-head, " +
    ".co-stats small, .us-detail small, .legend span, .sim-tiles small, .ck-grid b, .adv-card small, .mk-chart-head small, .hero .kicker, .ck small, .sec-note, .mk-note, " +
    ".vt > small, .cb-sub, .sim-book small, #sim-form label, .fd-cells small, .pk-sec h2, .pk-tile small";
  const done = new Set();

  function scan(root = document) {
    for (const el of root.querySelectorAll(SEL)) {
      if (el.closest("button, a, summary, .gl-pop") || el.dataset.gl || (el.textContent || "").length > 40) continue;
      el.dataset.gl = "1";
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const m = node.nodeValue.match(re);
        if (!m) continue;
        const gi = index[m[0]];
        if (done.has(gi)) continue;
        done.add(gi);
        const b = document.createElement("button");
        b.type = "button";
        b.className = "gl-q";
        b.dataset.g = gi;
        b.setAttribute("aria-label", `什麼是${G[gi].t}？`);
        b.textContent = "?";
        // 問號放在這段文字的結尾（不插在字詞中間，也不跑到後面不相干的小字後面）
        node.parentNode.insertBefore(b, node.nextSibling);
        break;
      }
    }
  }

  const pop = document.createElement("div");
  pop.className = "gl-pop";
  pop.setAttribute("role", "dialog");
  pop.hidden = true;
  document.body.appendChild(pop);
  let owner = null, pinned = false, hideTimer = 0;

  function fill(g) {
    pop.replaceChildren();
    const add = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; n.textContent = text; pop.appendChild(n); return n; };
    const head = add("div", "gl-head", "");
    const h = document.createElement("b"); h.textContent = g.t; head.appendChild(h);
    const x = document.createElement("button"); x.type = "button"; x.className = "gl-x"; x.setAttribute("aria-label", "關閉"); x.textContent = "×";
    x.addEventListener("click", close); head.appendChild(x);
    add("p", "gl-what", g.what);
    if (g.calc) { add("small", "gl-k", "怎麼算"); add("p", "gl-calc", g.calc); }
    if (g.see) { add("small", "gl-k", "可以看出什麼"); add("p", "", g.see); }
    if (g.ex) { add("small", "gl-k ex", "舉例"); add("p", "gl-ex", g.ex); }
    if (g.warn) { add("small", "gl-k warn", "要注意"); add("p", "", g.warn); }
  }

  function place(btn) {
    if (innerWidth < 640) { pop.classList.add("sheet"); pop.style.left = pop.style.top = ""; return; }
    pop.classList.remove("sheet");
    // body 在大螢幕有 zoom：getBoundingClientRect 是畫面座標，要除以 zoom 才是 CSS 座標
    const z = btn.currentCSSZoom || 1;
    const r = btn.getBoundingClientRect();
    const W = innerWidth / z, H = innerHeight / z, w = pop.offsetWidth, h = pop.offsetHeight;
    let left = (r.left + r.width / 2) / z - w / 2;
    left = Math.max(8, Math.min(left, W - w - 8));
    let top = r.bottom / z + 8;
    if (top + h > H - 8) top = Math.max(8, r.top / z - h - 8);
    pop.style.left = `${left}px`;
    pop.style.top = `${top}px`;
  }

  function open(btn, pin) {
    clearTimeout(hideTimer);
    if (owner === btn && !pop.hidden) { pinned = pinned || pin; return; }
    owner?.setAttribute("aria-expanded", "false");
    owner = btn; pinned = pin;
    fill(G[btn.dataset.g]);
    pop.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    place(btn);
  }
  function close() {
    pop.hidden = true; pinned = false;
    owner?.setAttribute("aria-expanded", "false");
    owner = null;
  }
  const later = () => { clearTimeout(hideTimer); hideTimer = setTimeout(() => { if (!pinned) close(); }, 220); };

  document.addEventListener("click", (ev) => {
    const b = ev.target.closest(".gl-q");
    if (b) { ev.preventDefault(); ev.stopPropagation(); (owner === b && pinned) ? close() : open(b, true); return; }
    if (!pop.hidden && !ev.target.closest(".gl-pop")) close();
  }, true);
  if (matchMedia("(hover: hover) and (pointer: fine)").matches) {
    document.addEventListener("mouseover", (ev) => {
      const b = ev.target.closest(".gl-q");
      if (b) open(b, false);
      else if (ev.target.closest(".gl-pop")) clearTimeout(hideTimer);
    });
    document.addEventListener("mouseout", (ev) => { if (ev.target.closest(".gl-q, .gl-pop") && !pinned) later(); });
  }
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && !pop.hidden) { owner?.focus(); close(); } });
  addEventListener("scroll", () => { if (!pop.hidden && !pop.classList.contains("sheet")) close(); }, { passive: true });
  addEventListener("resize", () => { if (!pop.hidden) close(); });

  scan();
  // 模擬交易、AI 顧問這類事後才畫出來的內容，也一併掃
  let t = 0;
  const watch = document.querySelector("#sim-app, #adv-out, #adv-app, #fd-app");
  if (watch) new MutationObserver(() => { clearTimeout(t); t = setTimeout(() => scan(watch), 300); }).observe(watch, { childList: true, subtree: true });
})();
