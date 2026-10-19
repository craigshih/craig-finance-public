"""
「大佬持股」頁（/whales/）：十位知名投資人最新 13F 持股、這季的買賣、以及大佬持有的美股連到哪些台股供應鏈。
資料來自 whales.py 的 data/whales/latest.json；供應鏈關係來自 supply_map.py（每條都有新聞出處）。
"""

import json
from html import escape
from pathlib import Path

from market_page import TAB_SCRIPT, panel, tabs
from visuals import clean_names, stock_logo

CHANGE_CLASS = {"新買進": "new", "加碼": "add", "減碼": "cut", "出清": "exit", "持平": "flat"}


def e(x) -> str:
    return escape(str(x if x is not None else ""))


def load(path: Path) -> dict | None:
    try:
        return clean_names(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def usd(v: float) -> str:
    return f"{v / 1e8:,.1f} 億美元" if v >= 1e8 else f"{v / 1e6:,.0f} 百萬美元"


def badge(change: str | None, pct: float | None = None) -> str:
    if not change:
        return ""
    extra = f" {pct:+.0f}%" if pct is not None and change in ("加碼", "減碼") else ""
    return f'<span class="wb {CHANGE_CLASS.get(change, "flat")}">{e(change)}{e(extra)}</span>'


# 大佬介紹：只寫有公開紀錄可查的事實；「要留意」寫他的風格限制，避免只看光環
PROFILES = {
    "ackman": {
        "en": "Bill Ackman", "role": "潘興廣場資本（Pershing Square）創辦人",
        "bio": ["2004 年創立潘興廣場，以「激進投資人」聞名：買進大量股份後進董事會推動公司改革。",
                "組合通常只有約 10 檔，長抱希爾頓、Chipotle、Restaurant Brands 等成功案例。",
                "2020 年 3 月疫情初期用信用違約交換避險，數千萬美元的部位換回約 26 億美元獲利。"],
        "why": "持股極度集中、每一檔都公開說明理由（年報、投資人說明會），可以完整追蹤他的邏輯與後續結果。",
        "caveat": "也有重大失誤，例如 Valeant 虧損與做空康寶萊的長期纏鬥；集中持股代表看錯時影響很大。",
    },
    "druck": {
        "en": "Stanley Druckenmiller", "role": "Duquesne 家族辦公室",
        "bio": ["1981 年創立 Duquesne Capital，到 2010 年結束對外募資前，據報導年化報酬約 30%、沒有一年虧損。",
                "曾擔任索羅斯量子基金的首席操盤手，參與 1992 年放空英鎊一役。",
                "現在只管理自己的家族資金，仍按規定每季申報 13F。"],
        "why": "總體經濟（利率、資金流）出發的頂尖操盤手，對產業趨勢轉向很敏銳，常是市場主題的早期指標。",
        "caveat": "換股非常快，13F 晚 45 天公布，看到時他可能已經賣掉；適合看方向，不適合照抄。",
    },
    "tepper": {
        "en": "David Tepper", "role": "Appaloosa 創辦人",
        "bio": ["1993 年創立 Appaloosa，專長在危機中買進被錯殺的資產。",
                "2009 年金融海嘯谷底大舉買進美國銀行、花旗等銀行股，當年替基金賺進數十億美元。",
                "也是 NFL 卡羅萊納黑豹隊老闆。"],
        "why": "在市場恐慌時敢於逆向重押，紀錄可查；他的加碼方向常反映對景氣與政策底部的判斷。",
        "caveat": "部位隨景氣循環大幅調整，波動大；近年已把大部分資金轉為家族資金管理。",
    },
    "wood": {
        "en": "Cathie Wood", "role": "方舟投資（ARK Invest）創辦人",
        "bio": ["2014 年創立方舟投資，專注 AI、機器人、基因科技、區塊鏈等「破壞式創新」。",
                "很早公開看好特斯拉，旗艦 ETF（ARKK）在 2020 年大漲，2021～2022 年也大幅回落。",
                "每天公布 ETF 交易明細，透明度很高。"],
        "why": "是觀察「創新題材」資金流向的好指標：她買什麼，往往代表市場在追哪些新科技。",
        "caveat": "長期績效波動非常大，選股偏向高成長、尚未獲利的公司；適合當題材參考，不適合當穩健範本。",
    },
    "burry": {
        "en": "Michael Burry", "role": "Scion 資產管理",
        "bio": ["2005 年起用信用違約交換押注美國次貸崩盤，2008 年大賺，是電影《大賣空》的主角原型。",
                "以深度研究、逆向操作聞名，2019 年很早就買進遊戲驛站（GameStop）。"],
        "why": "擅長找出市場忽略的風險與被低估的冷門公司，逆向觀點常有參考價值。",
        "caveat": "2025 年 9 月之後沒有新的 13F，資料停在當時；他也常用選擇權表達看空，13F 看不出完整部位。",
    },
    "gates": {
        "en": "Bill & Melinda Gates Foundation Trust", "role": "蓋茲基金會信託",
        "bio": ["管理蓋茲基金會的捐贈資產，由比爾蓋茲的投資公司 Cascade 團隊操作。",
                "最大持股長期是波克夏（巴菲特多年來把自己的波克夏股票捐給基金會），還有微軟、廢棄物處理、鐵路等穩定型公司。",
                "基金會 2025 年宣布計畫在 2045 年前把資產用完後關閉。"],
        "why": "超長期、低週轉的「永久資本」，偏好有定價能力與穩定現金流的公司，風格接近巴菲特。",
        "caveat": "因為要持續捐款與在 2045 年前花完資產，賣出不一定代表看壞那家公司。",
    },
}
TRUMP_PROFILE = {
    "en": "Donald J. Trump", "role": "美國第 47 任總統、川普媒體科技（DJT）最大股東",
    "bio": ["房地產與品牌授權起家，2017～2021 年擔任第 45 任總統，2025 年起擔任第 47 任總統。",
            "透過信託持有川普媒體科技集團（Truth Social 母公司）約 41.5% 股份（SEC 13D）。",
            "依法須向政府道德辦公室申報個人證券交易（Form 278-T），申報顯示大量個股與債券買賣。"],
    "why": "值得追蹤的不是投資績效，而是政策與市場的交集：關稅、晶片、能源等政策會直接影響這些公司，申報內容也受到國會與媒體高度關注。",
    "caveat": "OGE 沒有說明交易是本人決定還是委託帳戶操作；申報最晚可晚 45 天，且只列金額區間。",
}


def avatar(pid: str, name: str, cls: str = "", prefix: str = "../") -> str:
    """全站統一的 Q 版頭像（chibi.py 產生）。"""
    return f'<img class="qava {cls}" src="{prefix}portraits/q/{e(pid)}.svg" alt="{e(name)}（Q 版插畫）" loading="lazy">'


def profiles(w: dict, trump: dict | None, prefix: str = "../") -> str:
    import investors

    cards = []
    for m in w["managers"]:
        inv = investors.BY_ID.get(m.get("investor") or "")
        if inv:
            pic, en, role = avatar(inv["id"], m["person"], "lg", prefix), inv["en"], m["fund"]
            bio, why, caveat = inv["bio"], inv["trust"], None
        else:
            p = PROFILES.get(m["id"])
            if not p:
                continue
            pic, en, role = avatar(m["id"], m["person"], "lg", prefix), p["en"], p["role"]
            bio, why, caveat = p["bio"], p["why"], p["caveat"]
        cards.append(_profile_card(m["person"], en, role, pic, bio, why, caveat, m["id"]))
    if trump:
        t = TRUMP_PROFILE
        cards.append(_profile_card("川普", t["en"], t["role"], avatar("trump", "川普", "lg", prefix), t["bio"], t["why"], t["caveat"], "trump"))
    return (f'<div class="wprof-grid">{"".join(cards)}</div>'
            '<p class="mk-note">介紹只寫有公開紀錄可查的事實；四位投資人（段永平、巴菲特、芒格、李錄）的完整介紹在'
            '<a href="../investors/index.html">四位投資人頁</a>。過去績效不代表未來，請把他們的持股當研究線索，不是買進清單。</p>'
            + GOTO_SCRIPT)


def _profile_card(name, en, role, pic, bio, why, caveat, target) -> str:
    goto = ('<a class="wgoto" href="#trump-sec" data-goto="trump">看他的交易 →</a>' if target == "trump"
            else f'<a class="wgoto" href="#wm-sec" data-goto="{e(target)}">看他的持股 →</a>')
    return (f'<article class="wprof"><header>{pic}<div><h3>{e(name)}</h3><small>{e(en)}</small><span class="wrole">{e(role)}</span></div></header>'
            f'<ul>{"".join(f"<li>{e(b)}</li>" for b in bio)}</ul>'
            f'<p class="wwhy"><b>為什麼值得參考</b>{e(why)}</p>'
            + (f'<p class="wcav"><b>要留意</b>{e(caveat)}</p>' if caveat else "")
            + goto + "</article>")


GOTO_SCRIPT = """<script>
document.addEventListener("click", (ev) => {
  const a = ev.target.closest("[data-goto]");
  if (!a) return;
  const id = a.dataset.goto;
  if (id !== "trump") document.querySelector(`[data-tabs="wm"] [data-tab="${CSS.escape(id)}"]`)?.click();
});
</script>"""


def leader_suppliers() -> dict[str, list[dict]]:
    """美股龍頭 → 台股（只有新聞出處核對過的關係）。台積電 ADR 直接對到台積電。"""
    from supply_map import SOURCES, TW_MAP

    out: dict[str, list[dict]] = {"TSM": [{"code": "2330", "name": "台積電", "relation": "本尊", "note": "台積電在美國掛牌的 ADR", "source": None}]}
    for code, t in TW_MAP.items():
        for leader, (rel, note, src) in t["links"].items():
            if rel == "同業" or src not in SOURCES:
                continue
            s = SOURCES[src]
            out.setdefault(leader, []).append({"code": code, "name": t["name"], "relation": rel, "note": note,
                                               "source": {"publisher": s[0], "date": s[1], "title": s[2], "url": s[3]}})
    return out


def tw_moves(supply: dict | None) -> dict[str, dict]:
    return {t["code"]: t for t in (supply or {}).get("tw", [])}


def holder_chips(holders: list[dict]) -> str:
    return "".join(f'<span class="wh {CHANGE_CLASS.get(h["change"] or "", "flat")}" title="{e(h["person"])}：占其組合 {h["weight"]:.1f}%">'
                   f'{avatar(h["id"], h["person"], "xs")}{e(h["person"])}{badge(h["change"], h.get("chg_pct"))}</span>' for h in sorted(holders, key=lambda h: -h["weight"]))


def live_us(ticker: str) -> str:
    """美股代號給前端抓即時價（site.js）；BRK/B 這類轉成 BRK.B。"""
    return f' data-live-us="{e(ticker.replace("/", "."))}"' if ticker else ""


def consensus(w: dict) -> str:
    rows = sorted(w["by_ticker"].values(), key=lambda t: (-t["n"], -t["buying"], -t["value"]))[:12]
    cards = "".join(
        f'<article class="wcard"{live_us(t["ticker"])}><header>{stock_logo(t["ticker"], t["name"], "美股", "")}<div><b>{e(t["ticker"])}</b><small>{e(t["name"].title())}<span class="wq" data-f="price"></span> <span data-f="pct"></span></small></div>'
        f'<span class="wn"><b>{t["n"]}</b> 位</span></header><div class="whs">{holder_chips(t["holders"])}</div>'
        f'<p class="wfoot">合計 {usd(t["value"])}・本季買進 {t["buying"]} 位／賣出 {t["selling"]} 位</p></article>' for t in rows)
    return f'<div class="wgrid">{cards}</div>'


def to_taiwan(w: dict, supply: dict | None, trump: dict | None = None) -> str:
    sup = leader_suppliers()
    moves = tw_moves(supply)
    rows = sorted((t for t in w["by_ticker"].values() if t["ticker"] in sup), key=lambda t: (-t["n"], -t["buying"]))
    if not rows:
        return '<p class="empty">這一季大佬持有的美股裡，還沒有供應鏈地圖已查證的龍頭。</p>'
    out = []
    for t in rows:
        tws = []
        for s in sup[t["ticker"]]:
            mv = moves.get(s["code"]) or {}
            chg = mv.get("chg_1d")
            src = s["source"]
            link = (f'<a href="{e(src["url"])}" target="_blank" rel="noopener" title="{e(src["title"] or src["publisher"])}"><img class="ui-ico xs" src="/ui/news.svg" alt=""> {e(src["publisher"])}</a>'
                    if src and src.get("url") else "")
            tws.append(f'<li>{stock_logo(s["code"], s["name"], None, "sm")}<span><b>{e(s["name"])}</b><small>{e(s["code"])}・{e(s["relation"])}・{e(s["note"])}</small></span>'
                       + (f'<i class="{"pos" if chg > 0 else "neg" if chg < 0 else ""}">{chg:+.2f}%</i>' if chg is not None else "")
                       + f'{link}</li>')
        tr = (trump or {}).get("by_ticker", {}).get(t["ticker"])
        tchip = (f'<span class="wh trump {"add" if tr["buys"] > tr["sells"] else "cut"}">川普 近期{"買進" if tr["buys"] > tr["sells"] else "賣出"} {max(tr["buys"], tr["sells"])} 筆</span>'
                 if tr else "")
        out.append(f'<article class="wchain"><div class="wus"{live_us(t["ticker"])}>{stock_logo(t["ticker"], t["name"], "美股", "lg")}'
                   f'<div><b>{e(t["ticker"])} <span class="wlive"><span data-f="price"></span> <span data-f="pct"></span></span></b>'
                   f'<small>{t["n"]} 位大佬持有・本季買進 {t["buying"]} 位</small><div class="whs">{holder_chips(t["holders"])}{tchip}</div></div></div>'
                   f'<div class="warrow" aria-hidden="true"></div><ul class="wtw">{"".join(tws)}</ul></article>')
    return ('<div class="wchains">' + "".join(out) + '</div><p class="mk-note">台股端只列供應鏈地圖裡有新聞或公司資料出處的關係（點報紙圖示看原文）；漲跌為最近交易日。</p>')


def quarter_moves(w: dict) -> str:
    buys, sells = [], []
    for m in w["managers"]:
        for r in m["holdings"]:
            if r["change"] in ("新買進", "加碼") and not r["option"]:
                buys.append((m, r))
        for r in m["exits"]:
            sells.append((m, r))
        for r in m["holdings"]:
            if r["change"] == "減碼" and not r["option"]:
                sells.append((m, r))

    def li(m, r):
        return (f'<li>{stock_logo(r.get("ticker") or r["cusip"], r["name"], "美股", "sm")}<span><b>{e(r.get("ticker") or r["name"])}</b>'
                f'<small>{e(m["person"])}・{usd(r["value"])}</small></span>{badge(r["change"], r.get("chg_pct"))}</li>')
    buys.sort(key=lambda x: -x[1]["value"])
    sells.sort(key=lambda x: -x[1]["value"])
    return ('<div class="two-col">'
            f'<div><h3 class="wh3">買進與加碼（依金額）</h3><ul class="wlist">{"".join(li(*x) for x in buys[:12]) or "<li class=empty>本季沒有</li>"}</ul></div>'
            f'<div><h3 class="wh3">減碼與出清（依金額）</h3><ul class="wlist">{"".join(li(*x) for x in sells[:12]) or "<li class=empty>本季沒有</li>"}</ul></div>'
            '</div>')


def manager_block(m: dict, top: int = 10) -> str:
    rows = [r for r in m["holdings"] if not r["option"]][:top]
    mx = max((r["weight"] for r in rows), default=1) or 1
    bars = "".join(
        f'<li>{stock_logo(r.get("ticker") or r["cusip"], r["name"], "美股", "sm")}<span class="wnm"><b>{e(r.get("ticker") or "—")}</b><small>{e(r["name"].title())}</small></span>'
        f'<span class="wbar"><i style="width:{r["weight"] / mx * 100:.1f}%"></i></span><span class="wpct">{r["weight"]:.1f}%</span>{badge(r["change"], r.get("chg_pct"))}</li>'
        for r in rows)
    exits = "、".join(e(r.get("ticker") or r["name"]) for r in m["exits"][:8])
    opts = [r for r in m["holdings"] if r["option"]]
    notes = ""
    if not rows and opts:
        notes += (f'<p class="wexit">這份申報只有選擇權部位：'
                  + "、".join(f'{e(r.get("ticker") or r["name"])} {"看跌" if r["option"] == "PUT" else "看漲"}' for r in opts[:8]) + "</p>")
    from datetime import date
    if (date.today() - date.fromisoformat(m["period"])).days > 200:
        notes += f'<p class="wexit">⚠︎ 最新申報停在 {e(m["period"])}，之後沒有新的 13F（可能已不需申報或停止申報），資料偏舊。</p>'
    return (f'<div class="wmgr"><div class="wmgr-head"><div class="wmgr-who">{avatar(m["id"], m["person"], "md")}<div><b>{e(m["person"])}</b><small>{e(m["fund"])}・{e(m["note"])}</small></div></div>'
            f'<div class="wmeta">持股期間 {e(m["period"])}・申報 {e(m["filed"])}・{len(m["holdings"])} 檔・{usd(m["total_value"])}'
            f'・<a href="{e(m["url"])}" target="_blank" rel="noopener">SEC 原始申報 ↗</a></div></div>'
            f'<ol class="wbars">{bars}</ol>' + notes
            + (f'<p class="wexit">本季出清：{exits}</p>' if exits else "")
            + (f'<p class="mk-note">比較基準：上一份申報（{e(m["prev_period"])}）</p>' if m.get("prev_period") else '<p class="mk-note">只有一份申報，無法比較增減</p>')
            + "</div>")


def managers(w: dict) -> str:
    ms = w["managers"]
    return (tabs("wm", [(m["id"], m["person"]) for m in ms], ms[0]["id"])
            + "".join(panel("wm", m["id"], manager_block(m), i == 0) for i, m in enumerate(ms)))


def money_range(lo: float, hi: float) -> str:
    f = lambda v: f"${v / 1e6:,.1f}M" if v >= 1e6 else f"${v / 1e3:,.0f}K"  # noqa: E731
    return f"{f(lo)}～{f(hi)}"


def trump_section(t: dict | None) -> str:
    if not t or not t.get("filings"):
        return '<p class="empty">川普的 OGE 申報暫時讀不到</p>'
    fl = [f for f in t["filings"] if f["parsed"]]
    djt = t.get("djt")
    head = (f'<div class="wtrump-head"><div class="wtrump-who">{avatar("trump", "川普", "xl")}<div><b>川普</b><small>Form 278-T・{len(t["filings"])} 份申報</small></div></div>'
            f'<div class="stat"><div class="stat-label">近 120 天股票交易</div><div class="stat-value">{t["n_trades"]:,}<span class="unit">筆</span></div>'
            f'<div class="stat-foot"><span>對到美股代號 {t["matched"]:,} 筆（只列這些）・最新交易日 {e(t["latest_trade"])}</span></div></div>')
    if djt:
        pct = f'{djt["percent"]:.1f}%' if djt.get("percent") is not None else "—"
        head += (f'<div class="stat"><div class="stat-label">{e(djt.get("issuer") or "川普媒體科技")}（DJT）持股比例</div><div class="stat-value">{pct}</div>'
                 f'<div class="stat-foot"><span>SEC {e(djt["form"])}・{e(djt["filed"])}・<a href="{e(djt["url"])}" target="_blank" rel="noopener">原始申報 ↗</a></span></div></div>')
    head += "</div>"

    def rows(items, side):
        out = []
        for a in items[:12]:
            n = a["buys"] if side == "buy" else a["sells"]
            lo, hi = (a["buy_lo"], a["buy_hi"]) if side == "buy" else (a["sell_lo"], a["sell_hi"])
            label = a["ticker"] or a["name"]
            out.append(f'<li{live_us(a["ticker"]) if a["ticker"] else ""}>{stock_logo(a["ticker"] or label, a["name"], "美股", "sm")}'
                       f'<span><b>{e(label)} <span class="wlive"><span data-f="pct"></span></span></b><small>{e(a["name"].title())}・{n} 筆・合計 {money_range(lo, hi)}・最近 {e(a["last"])}</small></span>'
                       f'<a class="wsrc" href="{e(a["url"])}" target="_blank" rel="noopener"><img class="ui-ico xs" src="/ui/doc.svg" alt=""> OGE 原文</a></li>')
        return "".join(out) or '<li class="empty">沒有</li>'
    cols = ('<div class="two-col">'
            f'<div><h3 class="wh3">淨買進（依筆數）</h3><ul class="wlist">{rows(t["net_buys"], "buy")}</ul></div>'
            f'<div><h3 class="wh3">淨賣出（依筆數）</h3><ul class="wlist">{rows(t["net_sells"], "sell")}</ul></div></div>')
    # 川普買進的美股 → 台股供應鏈
    sup = leader_suppliers()
    links = []
    for a in t["net_buys"]:
        for x in sup.get(a["ticker"] or "", [])[:4]:
            links.append(f'<span class="wh add">{e(a["ticker"])} → {e(x["name"])}（{e(x["relation"])}）</span>')
    chain = (f'<h3 class="wh3" style="margin-top:18px">川普買進的美股，台股供應鏈有誰</h3><div class="whs">{"".join(links)}</div>' if links else "")
    filings = "、".join(f'<a href="{e(f["url"])}" target="_blank" rel="noopener">{e(f["first"])}～{e(f["last"])}（{f["parsed"]}／{f["total"] or "?"} 筆）</a>' for f in fl[-6:])
    note = ('<p class="mk-note">來源：美國政府道德辦公室（OGE）公開的總統財產申報 Form 278-T。申報只列金額「區間」，表中合計是區間加總；'
            'PDF 是掃描檔，本站用文字辨識解析（括號內是解析出的股票交易數／申報總筆數，總數含債券），解析不到的不會亂猜，每一筆都可點文件圖示對照原文。'
            'OGE 沒有說明交易是本人決定還是委託帳戶操作；申報最晚可在交易後 45 天提出。依法這些資料不得用於商業或募款用途，本站僅供個人研究。'
            f'</p><p class="mk-note">最近解析的申報：{filings}</p>')
    return head + cols + chain + note


def render(w: dict | None, supply: dict | None, hero, section, trump: dict | None = None) -> str:
    if not w or not w.get("managers"):
        return hero("大佬持股", "資料準備中", "SEC 13F 資料下一次更新後就會出現。")
    latest = max(m["filed"] for m in w["managers"])
    body = hero("大佬持股", "大佬在買什麼？台股誰受惠？",
                f'{len(w["managers"])} 位知名投資人的 SEC 13F ＋ 川普的 OGE 申報・最新申報 {e(latest)}・每 3 小時檢查新申報・股價盤中即時',
                '<p class="hero-note">13F 是美國機構每季申報的美股多方持股，最晚在季末後 45 天公布，所以看到的是「上一季做了什麼」，不是即時動向；'
                '也不包含放空與非美股部位。每一筆都能點回 SEC 原始文件。</p>')
    body += '<main class="wrap">'
    body += section("他們是誰、為什麼值得參考", profiles(w, trump), f'{len(w["managers"])} 位大佬＋川普')
    body += section("大佬共同持有", consensus(w), "依持有人數排序")
    body += section("大佬持股 → 台股供應鏈", to_taiwan(w, supply, trump), "大佬持有的美股龍頭，連到已查證的台廠", ("../supply/index.html", "看完整供應鏈地圖"))
    body += '<div id="trump-sec"></div>' + section("川普在買賣什麼", trump_section(trump), "OGE 官方財產申報（Form 278-T）")
    body += section("這一季的動作", quarter_moves(w), "跟上一份 13F 比較")
    body += '<div id="wm-sec"></div>' + section("各別大佬的最新持股", managers(w), "前十大持股與占比")
    return body + "</main>" + TAB_SCRIPT


def holdings_whales(holdings: list[dict], w: dict | None) -> str:
    """只放在 /portfolio/：我的台股持股，是哪些大佬持有之美股龍頭的供應商。"""
    if not w:
        return ""
    sup = leader_suppliers()
    held = {h["code"]: h for h in holdings}
    rows = []
    for t in sorted(w["by_ticker"].values(), key=lambda t: -t["n"]):
        mine = [s for s in sup.get(t["ticker"], []) if s["code"] in held]
        for s in mine:
            rows.append(f'<li>{stock_logo(s["code"], held[s["code"]]["name"], None, "sm")}<span><b>{e(held[s["code"]]["name"])}</b>'
                        f'<small>{e(s["relation"])} {e(t["ticker"])}・{e(s["note"])}</small></span>'
                        f'<span class="whs">{holder_chips(t["holders"])}</span></li>')
    if not rows:
        return '<p class="empty">這一季大佬持有的美股龍頭裡，沒有你持股的已查證供應鏈關係。</p>'
    return f'<ul class="wlist mine">{"".join(rows)}</ul>'
