// 模擬交易頁的前端。所有計算以伺服器回傳為準，這裡只負責顯示與送單。
(() => {
  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => [...document.querySelectorAll(sel)];
  const fmt = (n, d = 0) => (n == null ? "—" : Number(n).toLocaleString("zh-TW", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const signed = (n) => (n == null ? "—" : (n > 0 ? "+" : "") + fmt(n));
  const pct = (x) => (x == null ? "—" : (x > 0 ? "+" : "") + (x * 100).toFixed(2) + "%");
  const pctN = (x) => (x == null ? "—" : (x > 0 ? "+" : "") + x.toFixed(2) + "%");
  const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const k of kids.flat()) if (k != null && k !== false && k !== "") n.append(k instanceof Node ? k : document.createTextNode(String(k)));
    return n;
  };
  const svgEl = (tag, attrs = {}) => {
    const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    return n;
  };

  // 企業 logo（Financial Modeling Prep 公開圖）：上市 .TW、上櫃 .TWO；沒有圖就顯示首字
  const logo = (code, name, market) => {
    const base = "https://financialmodelingprep.com/image-stock/";
    const urls = market === "上櫃" ? [`${base}${code}.TWO.png`] : [`${base}${code}.TW.png`, `${base}${code}.TWO.png`];
    const hue = [...code].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
    const wrap = el("span", { class: "logo sm", style: `--h:${hue}` }, el("b", {}, (name || code)[0]));
    const img = el("img", { src: urls[0], alt: "", loading: "lazy", referrerpolicy: "no-referrer" });
    let i = 0;
    img.addEventListener("error", () => { i += 1; if (urls[i]) img.src = urls[i]; else img.remove(); });
    wrap.append(img);
    return wrap;
  };

  // 台股手續費／證交稅，跟伺服器 functions/_lib/market.js 同一套規則，只用於下單前預估
  const taxRate = (code) => (/^00\w*B$/.test(code) ? 0 : code.startsWith("00") ? 0.001 : 0.003);
  const estimate = (code, side, price, shares) => {
    const amount = Math.round(price * shares);
    const fee = Math.max(shares % 1000 === 0 ? 20 : 1, Math.floor(amount * 0.001425));
    const tax = side === "sell" ? Math.floor(amount * taxRate(code)) : 0;
    return { amount, fee, tax, total: side === "buy" ? amount + fee : amount - fee - tax };
  };
  // 台股升降單位（跳動點），跟伺服器 functions/_lib/broker.js 同一套：ETF 未滿 50 元 0.01、以上 0.05
  const tick = (p, code = quote?.code || "") => (code.startsWith("00") ? (p < 50 ? 0.01 : 0.05)
    : p < 10 ? 0.01 : p < 50 ? 0.05 : p < 100 ? 0.1 : p < 500 ? 0.5 : p < 1000 ? 1 : 5);
  const snap = (p) => { const t = tick(p); return +(Math.round(p / t) * t).toFixed(2); };
  const md = (day) => (day ? `${Number(day.slice(5, 7))}/${Number(day.slice(8, 10))}` : "");

  async function api(path, body) {
    const res = await fetch(`/api/sim/${path}`, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({ error: "伺服器沒有回應" }));
    if (!res.ok) throw new Error(data.error || `錯誤 ${res.status}`);
    return data;
  }

  function toast(msg, bad = false) {
    const t = $("#sim-toast");
    t.textContent = msg;
    t.className = "toast show" + (bad ? " bad" : "");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => (t.className = "toast"), 4000);
  }

  let me = null, side = "buy", type = "market", quote = null, watchSet = new Set();

  // ---------- 帳戶 ----------
  function equityChart(points) {
    const svg = $("#sim-equity");
    svg.replaceChildren();
    svg.classList.toggle("empty", !points || points.length < 2);
    if (!points || points.length < 2) return;
    const vals = points.map((p) => p.total);
    const lo = Math.min(...vals, me.initial), hi = Math.max(...vals, me.initial), span = hi - lo || 1;
    const x = (i) => (i / (vals.length - 1)) * 300, y = (v) => 74 - ((v - lo) / span) * 66;
    const d = vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
    const up = vals[vals.length - 1] >= me.initial;
    svg.append(svgEl("line", { x1: 0, x2: 300, y1: y(me.initial), y2: y(me.initial), class: "eq-base" }));
    svg.append(svgEl("path", { d: `${d} L300 80 L0 80 Z`, class: `eq-area ${up ? "up" : "down"}` }));
    svg.append(svgEl("path", { d, class: `eq-line ${up ? "up" : "down"}` }));
  }

  function renderAccount() {
    $("#sim-total").textContent = fmt(me.total);
    $("#sim-total-sub").replaceChildren(
      "今日 ", el("b", { class: cls(me.day_pl) }, signed(me.day_pl)),
      "　總報酬 ", el("b", { class: cls(me.return_pct) }, pct(me.return_pct)),
      `　・${me.nickname}`);
    $("#sim-status").className = "sim-status " + (me.market_open ? "open" : "");
    $("#sim-status").textContent = me.market_open
      ? `● 盤中・即時報價 ${me.price_time ? me.price_time.slice(0, 3) + String(Number(me.price_time.slice(3, 5)) - (Number(me.price_time.slice(3, 5)) % 5)).padStart(2, "0") : ""}`
      : `${me.session}・${md(me.price_date)} ${me.price_date && me.session === "已收盤" ? "收盤價" : "最近收盤"}・現在下單會排入 ${md(me.next_day)} 開盤`;
    const unreal = me.holdings.reduce((a, h) => a + h.pl, 0);
    const tiles = [
      ["可用現金", fmt(me.cash), ""], ["持股市值", fmt(me.holdings_value), `${me.holdings.length} 檔`],
      ["未實現損益", signed(unreal), cls(unreal)], ["已實現損益", signed(me.realized), cls(me.realized)],
    ];
    $("#sim-tiles").replaceChildren(...tiles.map(([k, v, c]) =>
      el("div", { class: "sim-tile" }, el("small", {}, k), el("b", { class: ["pos", "neg"].includes(c) ? c : "" }, v),
        c && !["pos", "neg"].includes(c) ? el("i", {}, c) : "")));
    equityChart(me.equity);
    $("#n-holdings").textContent = me.holdings.length || "";
    const open = me.orders.filter((o) => o.status === "open").length;
    $("#n-orders").textContent = open || "";
    renderHoldings();
    renderOrders();
    renderTrades();
    $("#sim-nickname").value = me.nickname;
    renderTicket();
  }

  function renderHoldings() {
    const box = $("#sim-holdings");
    if (!me.holdings.length) {
      $("#sim-alloc").replaceChildren();
      box.replaceChildren(el("p", { class: "empty" }, "還沒有持股，到「下單」買第一檔吧。"));
      return;
    }
    const total = me.total || 1;
    const parts = [...me.holdings.map((h) => [h.name, h.value]), ["現金", me.cash]];
    const colors = ["#e3232c", "#ffc928", "#f28c28", "#ff7a8a", "#b8b2a3", "#7aa2d6", "#8dd3a7", "#c38bff"];
    $("#sim-alloc").replaceChildren(
      el("div", { class: "alloc-bar" }, ...parts.map(([, v], i) => el("i", { style: `width:${(v / total) * 100}%;background:${i === parts.length - 1 ? "#3a3a42" : colors[i % colors.length]}` }))),
      el("div", { class: "alloc-legend" }, ...parts.map(([n, v], i) => el("span", {}, el("i", { style: `background:${i === parts.length - 1 ? "#3a3a42" : colors[i % colors.length]}` }), `${n} ${((v / total) * 100).toFixed(1)}%`))));
    box.replaceChildren(...me.holdings.map((h) => el("article", { class: "sim-card" },
      el("header", {}, logo(h.code, h.name), el("div", {}, el("b", {}, h.name), el("small", {}, `${h.code}・${fmt(h.shares)} 股`)),
        el("div", { class: "r" }, el("b", {}, fmt(h.price, 2)), el("small", { class: cls(h.day_pct) }, h.day_pct != null ? `今日 ${pctN(h.day_pct)}` : h.source))),
      el("div", { class: "sim-card-row" },
        el("span", {}, "均價 ", el("b", {}, fmt(h.avg_cost, 2))), el("span", {}, "市值 ", el("b", {}, fmt(h.value))),
        el("span", {}, "損益 ", el("b", { class: cls(h.pl) }, `${signed(h.pl)}（${pct(h.pl_pct)}）`))),
      el("div", { class: "sim-card-act" },
        el("button", { type: "button", class: "btn ghost", onclick: () => pick({ code: h.code, name: h.name }, "sell", h.shares) }, "賣出"),
        el("button", { type: "button", class: "btn ghost", onclick: () => pick({ code: h.code, name: h.name }) }, "看走勢")))));
  }

  const STATUS = { open: "等待成交", filled: "已成交", cancelled: "已取消", expired: "已失效", failed: "失敗" };
  const ordLabel = (o) => `${o.kind === "market" ? "市價" : "限價"}${o.side === "buy" ? "買" : "賣"}`;
  function renderOrders() {
    const box = $("#sim-orders");
    box.replaceChildren(...(me.orders.length ? me.orders.map((o) => el("li", { class: `ord ${o.status}` },
      el("span", { class: "pill" }, ordLabel(o)),
      el("span", { class: "ord-main" }, `${o.code} ${o.name || ""} ${fmt(o.shares)} 股 @ ${o.kind === "market" ? "開盤價" : fmt(o.limit_price, 2)}`),
      el("small", {}, `${STATUS[o.status]}${o.note ? `・${o.note}` : ""}${o.status === "open" ? `・${o.session ? `${md(o.session)} ` : ""}當日有效（13:30 前）` : ""}`),
      o.status === "open" ? el("button", { type: "button", class: "btn ghost", onclick: () => cancel(o.id) }, "取消") : ""))
      : [el("li", { class: "empty" }, "沒有委託。限價單沒有立刻成交、或非交易時間下的預約單，會出現在這裡。")]));
  }

  function renderTrades() {
    $("#sim-trades").replaceChildren(...(me.trades.length ? me.trades.map((t) =>
      el("li", {}, el("span", { class: `pill ${t.side}` }, t.side === "buy" ? "買進" : "賣出"),
        el("span", { class: "ord-main" }, `${t.code} ${t.name || ""} ${fmt(t.shares)} 股 @ ${fmt(t.price, 2)}`),
        el("small", {}, `${t.ts.slice(0, 16).replace("T", " ")}・手續費 ${fmt(t.fee)}${t.tax ? `・稅 ${fmt(t.tax)}` : ""}・${t.price_date || ""}`)))
      : [el("li", { class: "empty" }, "還沒有成交紀錄")]));
  }

  // 排行榜放在最上面的帳戶區塊：前 5 名＋自己的名次
  async function loadBoard() {
    const { rows } = await api("leaderboard");
    const mine = rows.findIndex((r) => r.me);
    const show = rows.slice(0, 5).map((r, i) => [r, i]);
    if (mine >= 5) show.push([rows[mine], mine]);
    const li = ([r, i]) => el("li", { class: r.me ? "me" : "" },
      el("span", { class: "rk" }, i < 3 ? ["🥇", "🥈", "🥉"][i] : String(i + 1)),
      el("b", {}, r.nickname, r.me ? el("small", {}, "（我）") : ""),
      el("span", { class: "num" }, fmt(r.total)),
      el("span", { class: "num " + cls(r.return_pct) }, pct(r.return_pct)));
    $("#sim-board").replaceChildren(...show.map(li));
    $("#sim-board-note").textContent = mine >= 0 ? `共 ${rows.length} 位・我排第 ${mine + 1} 名` : `共 ${rows.length} 位`;
  }

  async function loadWatch() {
    const box = $("#sim-watch");
    try {
      const { rows } = await api("watch");
      watchSet = new Set(rows.map((r) => r.code));
      $("#n-watch").textContent = rows.length || "";
      box.replaceChildren(...(rows.length ? rows.map((r) => el("article", { class: "sim-card click", onclick: () => pick(r) },
        el("header", {}, logo(r.code, r.name, r.market), el("div", {}, el("b", {}, r.name), el("small", {}, `${r.code}・${r.market}`)),
          el("div", { class: "r" }, el("b", {}, fmt(r.price, 2)), el("small", { class: cls(r.pct) }, r.pct != null ? pctN(r.pct) : `${r.date} 收盤`))),
        r.signals ? verdictBadge(r.signals) : el("small", { class: "muted" }, "體檢資料暫時讀不到")))
        : [el("p", { class: "empty" }, "還沒有自選股")]));
      updateStar();
    } catch (e) {
      box.replaceChildren(el("p", { class: "empty" }, e.message));
    }
  }

  async function refresh() {
    me = await api("me");
    renderAccount();
    loadBoard().catch(() => {});
  }

  // ---------- 搜尋 ----------
  let searchTimer = null, suggestions = [], active = -1;
  function showSuggest(rows) {
    suggestions = rows;
    active = rows.length ? 0 : -1;
    const ul = $("#sim-suggest");
    ul.hidden = !rows.length;
    ul.replaceChildren(...rows.map((r, i) => el("li", { role: "option", class: i === active ? "on" : "", onmousedown: (e) => { e.preventDefault(); pick(r); } },
      logo(r.code, r.name, r.market), el("b", {}, r.name), el("span", {}, r.code), el("small", {}, r.market))));
  }
  async function search(q) {
    if (!q.trim()) return showSuggest([]);
    try {
      const { rows } = await api(`search?q=${encodeURIComponent(q)}`);
      if ($("#sim-q").value === q) showSuggest(rows);
    } catch { showSuggest([]); }
  }

  // ---------- 股票資訊卡 ----------
  function verdictBadge(s) {
    const icon = { watch: "✓", retreat: "✕", neutral: "–" }[s.verdict];
    return el("div", { class: `verdict ${s.verdict}` }, el("i", {}, icon), el("span", {}, s.verdict_note),
      el("small", {}, `${s.trend}・量${s.volume}・${s.intraday}`));
  }

  function chartSvg(rows) {
    const W = 640, H = 260, VH = 60, pad = 46;
    const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H + VH}`, class: "kchart", role: "img", "aria-label": "日 K 線與均線" });
    const lo = Math.min(...rows.map((r) => Math.min(r.low, r.ma60 ?? r.low))), hi = Math.max(...rows.map((r) => Math.max(r.high, r.ma60 ?? r.high)));
    const span = hi - lo || 1, cw = (W - pad) / rows.length;
    const y = (v) => 8 + ((hi - v) / span) * (H - 24);
    const vmax = Math.max(...rows.map((r) => r.volume)) || 1;
    for (let k = 0; k <= 3; k++) {
      const v = lo + (span * k) / 3;
      svg.append(svgEl("line", { x1: 0, x2: W - pad, y1: y(v), y2: y(v), class: "grid" }));
      const t = svgEl("text", { x: W - pad + 4, y: y(v) + 4, class: "ax" });
      t.textContent = fmt(v, v < 100 ? 2 : 0);
      svg.append(t);
    }
    rows.forEach((r, i) => {
      const x = i * cw + cw / 2, up = r.close >= r.open;
      const g = svgEl("g", { class: up ? "up" : "down" });
      g.append(svgEl("line", { x1: x, x2: x, y1: y(r.high), y2: y(r.low) }));
      const top = y(Math.max(r.open, r.close)), bot = y(Math.min(r.open, r.close));
      g.append(svgEl("rect", { x: x - cw * 0.35, y: top, width: cw * 0.7, height: Math.max(bot - top, 0.8) }));
      const vh = (r.volume / vmax) * (VH - 6);
      g.append(svgEl("rect", { x: x - cw * 0.35, y: H + VH - vh, width: cw * 0.7, height: vh, class: "vol" }));
      svg.append(g);
    });
    for (const [key, cl] of [["ma5", "ma5"], ["ma20", "ma20"], ["ma60", "ma60"]]) {
      const pts = rows.map((r, i) => (r[key] == null ? null : `${(i * cw + cw / 2).toFixed(1)},${y(r[key]).toFixed(1)}`)).filter(Boolean);
      if (pts.length > 1) svg.append(svgEl("polyline", { points: pts.join(" "), class: `ma ${cl}` }));
    }
    return svg;
  }

  function stockCard(q, ch) {
    const s = ch?.signals;
    const star = el("button", { type: "button", class: "star", id: "sim-star", title: "加入自選", onclick: toggleWatch }, el("img", { src: "/ui/star-off.svg", alt: "加入自選" }));
    const head = el("div", { class: "sim-stock-head" }, logo(q.code, q.name, q.market),
      el("div", {}, el("h3", {}, q.name, " ", el("small", {}, q.code)),
        el("small", {}, `${q.market}・${q.source === "即時" ? "盤中即時" : `${md(q.date)} 收盤`}${q.time ? `・資料時間 ${window.hm5 ? hm5(q.time) : ""}` : ""}`)),
      el("div", { class: "r" }, el("b", { class: cls(q.chg) }, fmt(q.price, 2)), q.pct != null ? el("small", { class: cls(q.chg) }, `${signed(q.chg)}（${pctN(q.pct)}）`) : ""),
      star);
    const parts = [head];
    const cell = (k, v, c = "") => el("div", {}, el("small", {}, k), el("b", { class: c }, v));
    parts.push(el("div", { class: "sim-book" },
      cell("開盤", fmt(q.open, 2)), cell("最高", fmt(q.high, 2), "pos"), cell("最低", fmt(q.low, 2), "neg"),
      cell("昨收", fmt(q.prev, 2)), cell("買進", fmt(q.bid, 2)), cell("賣出", fmt(q.ask, 2)),
      cell("漲停", fmt(q.upper, 2), "pos"), cell("跌停", fmt(q.lower, 2), "neg"), cell("成交量", q.volume != null ? `${fmt(q.volume)} 張` : "—")));
    if (ch?.rows?.length) {
      const last = ch.rows[ch.rows.length - 1];
      parts.push(el("div", { class: "kwrap" }, chartSvg(ch.rows.slice(-90))),
        el("div", { class: "klegend" }, el("span", { class: "ma5" }, `5 日線 ${fmt(last.ma5, 2)}`), el("span", { class: "ma20" }, `20 日線 ${fmt(last.ma20, 2)}`),
          el("span", { class: "ma60" }, `60 日線 ${fmt(last.ma60, 2)}`), el("span", {}, `成交量 ${fmt(last.volume / 1000)} 張`)));
    } else {
      parts.push(el("p", { class: "muted" }, "走勢資料讀取中或暫時讀不到"));
    }
    if (s) {
      parts.push(el("div", { class: "checkup" },
        el("h4", {}, "四指標體檢 ", el("small", {}, `資料日 ${s.date}`)),
        el("div", { class: "ck-grid" },
          el("div", { class: "ck" }, el("small", {}, "① 趨勢（均線）"), el("b", {}, s.trend), el("i", {}, s.trend_note)),
          el("div", { class: "ck" }, el("small", {}, "② 量能（成交量）"), el("b", {}, `${s.volume}${s.vol_ratio ? ` ×${s.vol_ratio}` : ""}`), el("i", {}, s.volume_note || "今日量 ÷ 前 20 日均量")),
          el("div", { class: "ck" }, el("small", {}, "③ 日內強弱"), el("b", {}, s.intraday), el("i", {}, `收盤在當日高低區間的 ${Math.round(s.intraday_pos * 100)}% 位置`))),
        verdictBadge(s),
        el("p", { class: "sim-note" }, "④ 組合規則：均線走強＋量能溫和放大＝可加入觀察名單；均線破位＋量能下滑＝先撤退再說。只是教學用的規則判斷，不是買賣建議。")));
    }
    return el("div", { class: "sim-stock-card" }, ...parts);
  }

  function updateStar() {
    const s = $("#sim-star");
    if (!s || !quote) return;
    const on = watchSet.has(quote.code);
    s.querySelector("img").src = on ? "/ui/star-on.svg" : "/ui/star-off.svg";
    s.classList.toggle("on", on);
    s.title = on ? "從自選移除" : "加入自選";
  }

  async function toggleWatch() {
    if (!quote) return;
    const on = !watchSet.has(quote.code);
    try {
      await api("watch", { code: quote.code, on });
      toast(on ? `${quote.name} 已加入自選` : `${quote.name} 已移出自選`);
      await loadWatch();
    } catch (e) { toast(e.message, true); }
  }

  async function pick(r, s, shares) {
    showSuggest([]);
    $("#sim-q").value = `${r.name}（${r.code}）`;
    switchTab("trade");
    if (s) setSide(s);
    if (shares) $("#sim-shares").value = shares;
    $("#sim-stock").replaceChildren(el("div", { class: "sim-loading" }, "讀取中…"));
    try {
      quote = await api(`quote?code=${encodeURIComponent(r.code)}`);
    } catch (e) {
      quote = null;
      $("#sim-stock").replaceChildren(el("p", { class: "empty" }, e.message));
      renderTicket();
      return;
    }
    $("#sim-limit").value = snap(quote.price);
    $("#sim-stock").replaceChildren(stockCard(quote, null));
    updateStar();
    renderTicket();
    $("#sim-stock").scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      const ch = await api(`chart?code=${encodeURIComponent(r.code)}`);
      if (quote?.code === r.code) { $("#sim-stock").replaceChildren(stockCard(quote, ch)); updateStar(); }
    } catch { /* 沒有走勢也能下單 */ }
  }

  // ---------- 下單 ----------
  const orderPrice = () => (type === "limit" ? Number($("#sim-limit").value) : quote?.price);
  function renderTicket() {
    const box = $("#sim-ticket-stock");
    box.replaceChildren(quote ? el("span", {}, logo(quote.code, quote.name, quote.market), el("b", {}, `${quote.name} ${quote.code}`), el("small", {}, `現價 ${fmt(quote.price, 2)}`))
      : el("span", { class: "muted" }, "先搜尋股票"));
    $$(".lim").forEach((n) => (n.hidden = type !== "limit"));
    const held = quote ? me?.holdings.find((h) => h.code === quote.code)?.shares || 0 : 0;
    const p = orderPrice();
    const max = side === "buy" && p ? Math.floor((me?.cash || 0) / (p * 1.001425)) : held;
    $("#sim-maxbuy").textContent = quote ? (side === "buy" ? `最多可買約 ${fmt(max)} 股` : `持有 ${fmt(held)} 股`) : "";
    const shares = Number($("#sim-shares").value);
    const est = $("#sim-estimate");
    if (!quote || !Number.isInteger(shares) || shares < 1 || !p) {
      est.replaceChildren(el("span", { class: "muted" }, quote ? "輸入股數後顯示預估金額" : "搜尋股票後開始下單"));
    } else {
      const c = estimate(quote.code, side, p, shares);
      est.replaceChildren(
        el("div", {}, "成交金額", el("b", {}, fmt(c.amount))), el("div", {}, "手續費", el("b", {}, fmt(c.fee))),
        side === "sell" ? el("div", {}, "證交稅", el("b", {}, fmt(c.tax))) : "",
        el("div", { class: "est-total" }, side === "buy" ? "需付" : "實收", el("b", {}, fmt(c.total))),
        el("small", {}, side === "buy" ? `買完剩現金 ${fmt((me?.cash || 0) - c.total)}` : `賣完剩 ${fmt(held - shares)} 股`));
    }
    const band = quote ? `可委託 ${fmt(quote.order_lower, 2)}～${fmt(quote.order_upper, 2)}・每檔 ${tick(Number($("#sim-limit").value) || quote.price)} 元` : "";
    const lotWarn = Number.isInteger(shares) && shares >= 1000 && shares % 1000 ? "　⚠️ 整股（1,000 股倍數）和零股（1～999 股）要分開下單。" : "";
    $("#sim-note").textContent = (me?.market_open
      ? type === "limit"
        ? `限價單（ROD 當日有效）：買單在賣價 ≤ 委託價、賣單在買價 ≥ 委託價時成交，13:30 前沒成交自動失效。${band}`
        : "市價單：買進以當下最佳賣價成交、賣出以最佳買價成交（跟券商一樣，漲停鎖住買不到、跌停鎖住賣不掉）。"
      : type === "limit"
        ? `現在是${me?.session || "非交易時間"}：限價單會成為 ${md(quote?.order_day)} 的預約單，開盤價或盤中到價就成交。${band}`
        : `現在是${me?.session || "非交易時間"}：市價單會成為 ${md(quote?.order_day)} 的預約單，以開盤價成交。`) + lotWarn;
    $("#sim-submit").textContent = `${type === "limit" ? "送出限價" : "送出"}${side === "buy" ? "買單" : "賣單"}`;
  }

  function setSide(s) {
    side = s;
    $$("#sim-side button").forEach((b) => b.classList.toggle("on", b.dataset.side === s));
    $("#sim-submit").className = "btn " + (s === "buy" ? "buy" : "sell");
    renderTicket();
  }

  async function submit(ev) {
    ev.preventDefault();
    if (!quote) return toast("先搜尋要交易的股票", true);
    const shares = Number($("#sim-shares").value);
    const body = { code: quote.code, side, shares, type, limit_price: type === "limit" ? Number($("#sim-limit").value) : undefined };
    const btn = $("#sim-submit");
    btn.disabled = true;
    try {
      const r = await api("order", body);
      toast(r.filled
        ? `✅ ${r.side === "buy" ? "買進" : "賣出"} ${r.name} ${fmt(r.shares)} 股 @ ${fmt(r.price, 2)}（${r.source}）${r.realized != null ? `・實現損益 ${signed(r.realized)}` : ""}`
        : `📝 ${r.message}：${r.name} ${fmt(r.shares)} 股${r.kind === "limit" ? ` @ ${fmt(r.limit_price, 2)}` : ""}`);
      await refresh();
      if (!r.filled) switchTab("orders");
    } catch (e) {
      toast(e.message, true);
    } finally {
      btn.disabled = false;
    }
  }

  async function cancel(id) {
    try {
      await api("cancel", { id });
      toast("委託已取消");
      await refresh();
    } catch (e) { toast(e.message, true); }
  }

  function switchTab(name) {
    $$("#sim-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
    $$(".sim-panel").forEach((p) => (p.hidden = p.dataset.panel !== name));
    if (name === "watch") loadWatch();
  }

  function init() {
    if (!$("#sim-app")) return;
    $$("#sim-tabs button").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
    const q = $("#sim-q");
    q.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => search(q.value), 180); });
    q.addEventListener("focus", () => { if (q.value.includes("（")) q.select(); });
    q.addEventListener("blur", () => setTimeout(() => showSuggest([]), 150));
    q.addEventListener("keydown", (e) => {
      if (e.isComposing) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        if (!suggestions.length) return;
        active = (active + (e.key === "ArrowDown" ? 1 : -1) + suggestions.length) % suggestions.length;
        $$("#sim-suggest li").forEach((li, i) => li.classList.toggle("on", i === active));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (suggestions[active]) pick(suggestions[active]);
        else api(`search?q=${encodeURIComponent(q.value)}`).then(({ rows }) => rows[0] ? pick(rows[0]) : toast("找不到這檔股票", true));
      } else if (e.key === "Escape") showSuggest([]);
    });
    // 熱門快選
    $("#sim-hot").replaceChildren(el("small", {}, "熱門："), ...[["2330", "台積電"], ["2317", "鴻海"], ["2454", "聯發科"], ["0050", "元大台灣50"], ["0056", "元大高股息"], ["00878", "國泰永續高股息"]]
      .map(([code, name]) => el("button", { type: "button", class: "chip", onclick: () => pick({ code, name }) }, name)));

    $("#sim-form").addEventListener("submit", submit);
    $("#sim-shares").addEventListener("input", renderTicket);
    $("#sim-limit").addEventListener("input", renderTicket);
    $$("#sim-side button").forEach((b) => b.addEventListener("click", () => setSide(b.dataset.side)));
    $$("#sim-type button").forEach((b) => b.addEventListener("click", () => {
      type = b.dataset.type;
      $$("#sim-type button").forEach((x) => x.classList.toggle("on", x === b));
      if (quote && !$("#sim-limit").value) $("#sim-limit").value = snap(quote.price);
      renderTicket();
    }));
    $$("[data-step]").forEach((b) => b.addEventListener("click", () => {
      const v = Number($("#sim-limit").value) || quote?.price || 0;
      const t = tick(Number(b.dataset.step) < 0 ? v - 1e-9 : v); // 往下跳過價位分界時用下一級的跳動點
      $("#sim-limit").value = snap(+(v + Number(b.dataset.step) * t).toFixed(2));
      renderTicket();
    }));
    $$("[data-shares]").forEach((b) => b.addEventListener("click", () => {
      const v = Number($("#sim-shares").value) || 0;
      const step = v >= 1000 && v % 1000 === 0 ? 1000 : 1;
      $("#sim-shares").value = Math.max(1, v + Number(b.dataset.shares) * step);
      renderTicket();
    }));
    $$("[data-lots]").forEach((b) => b.addEventListener("click", () => {
      $("#sim-shares").value = Math.round(Number(b.dataset.lots) * 1000);
      renderTicket();
    }));
    $("[data-frac]").addEventListener("click", () => {
      if (!quote) return;
      const held = me?.holdings.find((h) => h.code === quote.code)?.shares || 0;
      const p = orderPrice();
      $("#sim-shares").value = side === "sell" ? held : Math.max(0, Math.floor((me?.cash || 0) / (p * 1.001425)) - 1);
      renderTicket();
    });
    $("#sim-nick-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("nickname", { nickname: $("#sim-nickname").value });
        toast("暱稱已更新");
        await refresh();
      } catch (err) { toast(err.message, true); }
    });
    $("#sim-reset").addEventListener("click", async () => {
      if (!confirm("確定要重新開始？持股、委託和成交紀錄會清空，資金回到 1,000,000（自選股會保留）。")) return;
      try {
        await api("reset", {});
        toast("已重新開始");
        await refresh();
      } catch (err) { toast(err.message, true); }
    });
    setSide("buy");
    refresh().catch((e) => {
      $("#sim-app").prepend(el("div", { class: "soon" }, `讀不到帳戶：${e.message}`));
    });
    loadWatch();
    // 盤中每 30 秒更新帳戶（即時價、委託撮合）；切回這個分頁時也立刻更新一次
    setInterval(() => { if (!document.hidden && me?.market_open) refresh().catch(() => {}); }, 30_000);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh().catch(() => {}); });
  }

  init();
})();
