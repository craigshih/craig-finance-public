"""
/supply/ 供應鏈地圖頁面：
  1. 本日最強龍頭 → 點選龍頭 → 以龍頭為中心的關係圖＋台股清單
  2. 被最多美國龍頭採用的台股 → 點選台股 → 以台股為中心的關係圖＋它供應的龍頭
每條關係都附出處（supply_map.SOURCES）；另有每天從鉅亨網 RSS 自動收集的近期新聞佐證。
資料：data/supply/latest.json（supply.py 產生）。切換龍頭由 static/site.js 處理，不用重新載入頁面。
"""

import json
import math
from pathlib import Path

from supply_map import LEADERS, PEER_GROUPS, SOURCES
from visuals import clean_names, e, sparkline, stock_logo

REL_CLASS = {"供應商": "sup", "客戶": "cus", "同業": "peer", "合作": "part", "台股同業": "twp"}
REL_NOTE = {
    "供應商": "台廠賣產品或代工給它：它的需求好，台廠訂單可能跟著好",
    "客戶": "台廠向它買設備：台廠擴產時它受惠，方向相反",
    "同業": "同產業、景氣連動（例如記憶體報價）",
    "合作": "合資、代理或共同開發",
    "台股同業": "同一族群的台灣競爭者（新聞把它們放在一起比較）",
}
REL_ORDER = {"供應商": 0, "合作": 1, "客戶": 2, "同業": 3}


def sources_links(keys: list[str]) -> str:
    out = []
    for k in keys:
        pub, date, title, url, quote = SOURCES[k]
        tip = "　".join(x for x in [f"{pub} {date}".strip(), title, f"原文：「{quote}」" if quote else ""] if x)
        out.append(f'<a class="src-link" href="{e(url)}" target="_blank" rel="noopener" title="{e(tip)}"><img class="ui-ico xs" src="/ui/news.svg" alt=""> {e(pub)}{" " + e(date[:7]) if date else ""}</a>')
    return " ".join(out)


def peer_compare(t: dict, tw_by_code: dict) -> str:
    """同業比較：依族群分組，今天漲跌的長條（自己加粗），附族群出處。"""
    blocks = []
    for group, members, srcs in PEER_GROUPS:
        if t["code"] not in {c for c, _ in members}:
            continue
        rows = sorted((tw_by_code[c] for c, _ in members if c in tw_by_code), key=lambda x: -(x.get("chg_1d") or 0))
        top = max((abs(x.get("chg_1d") or 0) for x in rows), default=1) or 1
        lis = "".join(
            f'<li class="{"me" if x["code"] == t["code"] else ""}">{stock_logo(x["code"], x["name"], x["market"], "sm")}'
            f'<span class="pc-name">{e(x["name"])}<small>{e(x["code"])}</small></span>'
            f'<span class="pc-bar"><i class="{"pos" if (x.get("chg_1d") or 0) > 0 else "neg"}" style="--w:{abs(x.get("chg_1d") or 0) / top * 100:.0f}%"></i></span>'
            f'<span class="num">{pct_span(x.get("chg_1d"))}</span><span class="num muted">5 日 {pct_span(x.get("chg_5d"), 1)}</span></li>'
            for x in rows)
        blocks.append(f'<div class="pgroup"><div class="pg-head"><b>{e(group)}</b>{sources_links(srcs)}</div><ul class="pcomp">{lis}</ul></div>')
    if not blocks:
        return ""
    return f'<h4 class="sub-h">台股同業／競爭者</h4><div class="pgroups">{"".join(blocks)}</div>'


def group_overview(tw_by_code: dict) -> str:
    """每個族群今天的表現：平均漲跌＋成員長條。"""
    cards = []
    for group, members, srcs in PEER_GROUPS:
        rows = sorted((tw_by_code[c] for c, _ in members if c in tw_by_code), key=lambda x: -(x.get("chg_1d") or 0))
        if not rows:
            continue
        avg = sum(x.get("chg_1d") or 0 for x in rows) / len(rows)
        top = max((abs(x.get("chg_1d") or 0) for x in rows), default=1) or 1
        lis = "".join(
            f'<li>{stock_logo(x["code"], x["name"], x["market"], "sm")}<span class="pc-name">{e(x["name"])}</span>'
            f'<span class="pc-bar"><i class="{"pos" if (x.get("chg_1d") or 0) > 0 else "neg"}" style="--w:{abs(x.get("chg_1d") or 0) / top * 100:.0f}%"></i></span>'
            f'<span class="num">{pct_span(x.get("chg_1d"), 1)}</span></li>' for x in rows)
        cards.append((avg, f'<div class="gcard"><div class="pg-head"><b>{e(group)}</b><span class="gavg">平均 {pct_span(avg)}</span></div>'
                           f'<ul class="pcomp">{lis}</ul><div class="g-src">{sources_links(srcs)}</div></div>'))
    cards.sort(key=lambda x: -x[0])
    return f'<div class="gcards">{"".join(c for _, c in cards)}</div>'


def source_link(src: str | None, news: list[dict] | None = None) -> str:
    """出處連結：滑過去看媒體、日期、標題與原文摘錄；另外列出自動收集的近期新聞數。"""
    if not src:
        return '<span class="src-peer" title="同業依產品線分類，不是供應關係">產業分類</span>'
    pub, date, title, url, quote = SOURCES[src]
    tip = "　".join(x for x in [f"{pub} {date}".strip(), title, f"原文：「{quote}」" if quote else ""] if x)
    more = (f'<span class="ev" title="{e(chr(10).join(n["date"] + " " + n["title"] for n in news))}">＋{len(news)} 則近期新聞</span>'
            if news else "")
    return f'<a class="src-link" href="{e(url)}" target="_blank" rel="noopener" title="{e(tip)}"><img class="ui-ico xs" src="/ui/news.svg" alt=""> {e(pub)}{" " + e(date[:7]) if date else ""}</a>{more}'


def network(center: str, center_chg, nodes: list[dict], label: str) -> str:
    """關係圖：中心是一家公司，周圍一圈是跟它有關係的公司；線的樣式代表關係，圓點顏色代表今天漲跌。
    nodes: [{"name", "chg", "rel"}]"""
    w, h, cx, cy = 640, 440, 320, 220
    n = len(nodes)
    r = 165 if n > 8 else 140
    edges, circles = [], []
    for i, nd in enumerate(nodes):
        a = -math.pi / 2 + 2 * math.pi * i / n
        x, y = cx + r * math.cos(a) * 1.25, cy + r * math.sin(a)
        chg = nd.get("chg") or 0
        tone = "pos" if chg > 0 else "neg" if chg < 0 else "flat"
        edges.append(f'<line class="edge {REL_CLASS.get(nd["rel"], "sup")}" x1="{cx}" y1="{cy}" x2="{x:.0f}" y2="{y:.0f}" style="--i:{i}"/>')
        circles.append(
            f'<g class="node {tone}" style="--i:{i};--s:{min(abs(chg) / 4, 1):.2f}" transform="translate({x:.0f} {y:.0f})">'
            f'<circle r="21"/><text class="nn" y="-28">{e(nd["name"].replace("*", ""))}</text>'
            f'<text class="nc" y="5">{chg:+.1f}%</text></g>')
    c = (f'<g class="center" transform="translate({cx} {cy})"><circle r="44"/>'
         f'<text y="-4">{e(center.replace("*", ""))}</text><text class="cc" y="16">{(center_chg or 0):+.2f}%</text></g>')
    return f'<svg class="net" viewBox="0 0 {w} {h}" role="img" aria-label="{e(label)}">{"".join(edges)}{"".join(circles)}{c}</svg>'


def legend() -> str:
    return '<div class="legend rel-legend">' + "".join(
        f'<span><i class="ln {c}"></i>{e(k)}：{e(REL_NOTE[k])}</span>' for k, c in REL_CLASS.items()) + "</div>"


def load(path: Path) -> dict | None:
    return clean_names(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else None


def pct_span(x, digits=2) -> str:
    if x is None:
        return "—"
    cls = "pos" if x > 0 else "neg" if x < 0 else ""
    return f'<span class="{cls}">{x:+.{digits}f}%</span>'


def leader_logo(ld: dict, size: str = "sm") -> str:
    return stock_logo(LEADERS[ld["code"]][2], ld["name"], None, size)


def flow_cell(f: dict | None) -> str:
    if not f:
        return '<span class="muted">—</span>'
    net = (f.get("foreign_lots") or 0) + (f.get("trust_lots") or 0)
    cls = "pos" if net > 0 else "neg" if net < 0 else ""
    return f'<span class="{cls}">{net:+,}</span><small>張・{f.get("buy_days", 0)}/5 天買超</small>'


def leader_panel(ld: dict, rows: list[dict], selected: bool, evidence: dict) -> str:
    if not rows:
        return ""
    ups = sum(1 for t in rows if (t.get("chg_1d") or 0) > 0)
    avg = sum(t.get("chg_1d") or 0 for t in rows) / len(rows)
    us = ld["market"] == "美股"
    timing = ("美股收盤在台股開盤之前，可以對照「龍頭上一個交易日」與「台股今天」的反應。" if us
              else "日股、韓股和台股交易時間大致重疊，漲跌通常是同一天的反應。")
    rows = sorted(rows, key=lambda t: (REL_ORDER.get(t["links"][ld["code"]][0], 9), -(t.get("chg_1d") or 0)))
    trs = "".join(
        f'<tr><td><span class="name">{stock_logo(t["code"], t["name"], t["market"], "sm")}'
        f'<span><b>{e(t["name"])}</b><small>{e(t["code"])}・{e(t["market"])}</small></span></span></td>'
        f'<td><span class="rel {REL_CLASS.get(t["links"][ld["code"]][0], "sup")}">{e(t["links"][ld["code"]][0])}</span></td>'
        f'<td class="role">{e(t["links"][ld["code"]][1])}</td>'
        f'<td class="num">{pct_span(t.get("chg_1d"))}</td><td class="num">{pct_span(t.get("chg_5d"))}</td>'
        f'<td class="num flowc">{flow_cell(t.get("flows"))}</td>'
        f'<td class="sparkc">{sparkline(t.get("spark"), 100, 28)}</td>'
        f'<td class="srcc">{source_link(t["links"][ld["code"]][2], evidence.get(t["code"] + "|" + ld["code"]))}</td></tr>'
        for t in rows)
    net = network(ld["name"], ld["chg_1d"], [{"name": t["name"], "chg": t.get("chg_1d"), "rel": t["links"][ld["code"]][0]} for t in rows],
                  f'{ld["name"]}的台股供應鏈關係圖')
    return f"""<div class="lpanel" data-leader="{e(ld['code'])}"{'' if selected else ' hidden'}>
  <div class="lhead">{leader_logo(ld, 'lg')}
    <div><h3>{e(ld['name'])}<small>{e(ld['market'])}・{e(ld['industry'])}</small></h3>
    <p class="muted">最新收盤 {ld['price']:,.2f}（{e(ld['date'])}）・單日 {pct_span(ld['chg_1d'])}・5 日 {pct_span(ld['chg_5d'])}</p></div>
    <div class="lspark">{sparkline(ld.get('spark'), 220, 56)}</div></div>
  <p class="transmit"><b>傳導觀察</b>{len(rows)} 家台股相關公司今天平均 {pct_span(avg)}，{ups} 家上漲、{len(rows) - ups} 家下跌或平盤。{timing}</p>
  <div class="netwrap">{net}</div>
  {legend()}
  <div class="table-wrap"><table class="holdings chain"><thead><tr><th>台股公司</th><th>關係</th><th>角色</th><th class="num">今日</th><th class="num">5 日</th>
  <th class="num">法人 5 日（外資＋投信）</th><th>20 日走勢</th><th>出處</th></tr></thead><tbody>{trs}</tbody></table></div>
</div>"""


US_SUPPLY = ("供應商", "合作")


def us_links(t: dict, leaders: dict) -> list[str]:
    return [ld for ld, (rel, *_) in t["links"].items() if ld in leaders and leaders[ld]["market"] == "美股" and rel in US_SUPPLY]


def tw_panel(t: dict, leaders: dict, selected: bool, evidence: dict, tw_by_code: dict) -> str:
    links = sorted(((ld, *t["links"][ld]) for ld in t["links"] if ld in leaders),
                   key=lambda x: (REL_ORDER.get(x[1], 9), leaders[x[0]]["market"] != "美股", -(leaders[x[0]].get("chg_1d") or 0)))
    n_us = len(us_links(t, leaders))
    avg = sum(leaders[ld]["chg_1d"] or 0 for ld, *_ in links) / len(links)
    peer_codes = list(dict.fromkeys(p["code"] for p in t.get("peers", []) if p["code"] in tw_by_code))
    net = network(t["name"], t.get("chg_1d"),
                  [{"name": leaders[ld]["name"], "chg": leaders[ld]["chg_1d"], "rel": rel} for ld, rel, *_ in links]
                  + [{"name": tw_by_code[c]["name"], "chg": tw_by_code[c].get("chg_1d"), "rel": "台股同業"} for c in peer_codes],
                  f'{t["name"]}連到的海外龍頭與台股同業關係圖')
    trs = "".join(
        f'<tr><td><span class="name">{stock_logo(LEADERS[ld][2], leaders[ld]["name"], None, "sm")}'
        f'<span><b>{e(leaders[ld]["name"])}</b><small>{e(leaders[ld]["market"])}・{e(leaders[ld]["industry"])}</small></span></span></td>'
        f'<td><span class="rel {REL_CLASS.get(rel, "sup")}">{e(rel)}</span></td><td class="role">{e(role)}</td>'
        f'<td class="num">{pct_span(leaders[ld]["chg_1d"])}</td><td class="num">{pct_span(leaders[ld]["chg_5d"])}</td>'
        f'<td class="srcc">{source_link(src, evidence.get(t["code"] + "|" + ld))}</td></tr>'
        for ld, rel, role, src in links)
    return f"""<div class="lpanel tpanel" data-tw="{e(t['code'])}"{'' if selected else ' hidden'}>
  <div class="lhead">{stock_logo(t['code'], t['name'], t['market'], 'lg')}
    <div><h3>{e(t['name'])}<small>{e(t['code'])}・{e(t['market'])}</small></h3>
    <p class="muted">最新收盤 {t['price']:,.2f}（{e(t['date'])}）・單日 {pct_span(t.get('chg_1d'))}・5 日 {pct_span(t.get('chg_5d'))}</p></div>
    <div class="lspark">{sparkline(t.get('spark'), 220, 56)}</div></div>
  <p class="transmit"><b>連結摘要</b>出現在 {n_us} 家美國龍頭的供應鏈（供應或合作），總共連到 {len(links)} 家海外公司；
  這些龍頭最新一個交易日平均 {pct_span(avg)}，{e(t['name'])} 今天 {pct_span(t.get('chg_1d'))}。</p>
  <div class="netwrap">{net}</div>
  {legend()}
  <div class="table-wrap"><table class="holdings chain"><thead><tr><th>海外龍頭</th><th>關係</th><th>{e(t['name'])}的角色</th>
  <th class="num">龍頭今日</th><th class="num">龍頭 5 日</th><th>出處</th></tr></thead><tbody>{trs}</tbody></table></div>
  {peer_compare(t, tw_by_code)}
</div>"""


def render(data: dict | None, prefix: str = "../") -> str:
    from build import hero, section  # 避免循環匯入

    body = hero("供應鏈地圖", "海外龍頭 → 台股供應鏈",
                "看美股、日股、韓股龍頭今天怎麼走，順著供應鏈找到相關的台股公司。")
    body += '<main class="wrap" id="supply-app">'
    if not data or not data.get("leaders"):
        return body + '<p class="empty">供應鏈資料還沒產生</p></main>'
    leaders = sorted(data["leaders"], key=lambda l: -(l.get("chg_1d") or 0))
    by_leader = {l["code"]: [t for t in data["tw"] if l["code"] in (t.get("links") or {})] for l in leaders}
    top = leaders[0]["code"]

    strong = "".join(
        f'<button class="lcard{" on" if l["code"] == top else ""}" data-pick="{e(l["code"])}">{leader_logo(l)}'
        f'<span class="lc-name"><b>{e(l["name"])}</b><small>{e(l["market"])}・{len(by_leader[l["code"]])} 家台股</small></span>'
        f'<span class="lc-chg">{pct_span(l["chg_1d"])}</span>{sparkline(l.get("spark"), 120, 30)}</button>'
        for l in leaders[:6])
    body += section("本日最強龍頭", f'<div class="lcards">{strong}</div>', "依最新一個交易日漲幅排序，點一下看它的台股供應鏈")

    markets = ["全部", "美股", "日股", "韓股"]
    tabs = "".join(f'<button class="{"on" if m == "全部" else ""}" data-market="{m}">{m}</button>' for m in markets)
    chips = "".join(
        f'<button class="lchip{" on" if l["code"] == top else ""}" data-pick="{e(l["code"])}" data-mk="{e(l["market"])}">'
        f'{leader_logo(l)}<span>{e(l["name"])}</span>{pct_span(l["chg_1d"], 1)}</button>'
        for l in sorted(leaders, key=lambda l: (markets.index(l["market"]), -(l.get("chg_1d") or 0))))
    evidence = data.get("evidence") or {}
    panels = "".join(leader_panel(l, by_leader[l["code"]], l["code"] == top, evidence) for l in leaders)
    body += section("選一家龍頭", f'<div class="news-tabs" id="mk-tabs">{tabs}</div><div class="lchips">{chips}</div>{panels}',
                    f'法人資料 {e(data.get("flows_date") or "—")}（只涵蓋上市公司）')

    # 反向：被最多美國龍頭採用的台股
    names = {l["code"]: l for l in data["leaders"]}
    ranked = sorted((t for t in data["tw"] if us_links(t, names)),
                    key=lambda t: (-len(us_links(t, names)), -len(t["links"]), -(t.get("chg_1d") or 0)))
    if ranked:
        first = ranked[0]["code"]
        cards = "".join(
            f'<button class="lcard{" on" if t["code"] == first else ""}" data-tpick="{e(t["code"])}">'
            f'{stock_logo(t["code"], t["name"], t["market"], "sm")}'
            f'<span class="lc-name"><b>{e(t["name"])}</b><small>{len(us_links(t, names))} 家美國龍頭・{e(t["code"])}</small></span>'
            f'<span class="lc-chg">{pct_span(t.get("chg_1d"))}</span>'
            f'<span class="lc-logos">{"".join(stock_logo(LEADERS[ld][2], names[ld]["name"], None, "sm") for ld in us_links(t, names))}</span></button>'
            for t in ranked[:6])
        chips = "".join(
            f'<button class="lchip{" on" if t["code"] == first else ""}" data-tpick="{e(t["code"])}">'
            f'{stock_logo(t["code"], t["name"], t["market"], "sm")}<span>{e(t["name"])}</span><b class="cnt">{len(us_links(t, names))}</b></button>'
            for t in ranked)
        tw_by_code = {x["code"]: x for x in data["tw"]}
        tpanels = "".join(tw_panel(t, names, t["code"] == first, evidence, tw_by_code) for t in ranked)
        body += section("被最多美國龍頭採用的台股",
                        f'<div class="lcards">{cards}</div><p class="sec-note chips-note">全部 {len(ranked)} 檔（數字＝連到幾家美國龍頭）：</p>'
                        f'<div class="lchips">{chips}</div>{tpanels}',
                        "反過來看：以台股為中心，看它供應哪些美國龍頭，以及台灣的同業")
        body += section("台股族群今日表現", group_overview(tw_by_code), "同一族群的台灣競爭者，依族群平均漲幅排序")
    body += ('<p class="obs-disclaimer">每一條供應、客戶、合作關係都附有新聞或公司公告出處（點報紙圖示看原文），'
             '找不到出處的關係一律不放；「同業」是依產品線分類，不是供應關係。訂單與合作會變動，請留意出處日期。'
             '「近期新聞」是每天從鉅亨網 RSS 自動收集、標題同時點名雙方的新聞，只用來補充既有關係。'
             '股價來自 Yahoo Finance，法人買賣超來自證交所。這是研究素材，不是買賣建議。</p>')
    return body + "</main>"


# ---------- 我的持股 × 供應鏈（只放在有密碼的 /portfolio/） ----------

def holdings_exposure(holdings: list[dict], data: dict | None) -> str:
    """把投資頁的持股（Notion）對到供應鏈地圖：哪些海外龍頭跟我的持股連動、占多少市值。"""
    if not data or not holdings:
        return '<p class="empty">供應鏈資料或持股資料還沒準備好</p>'
    tw = {t["code"]: t for t in data["tw"]}
    leaders = {l["code"]: l for l in data["leaders"]}
    linked, unlinked = [], []
    for h in holdings:
        t = tw.get(h["code"])
        (linked if t and t["links"] else unlinked).append((h, t))

    expo: dict[str, dict] = {}
    for h, t in linked:
        for ld, (rel, role, *_) in t["links"].items():
            if ld not in leaders:
                continue
            x = expo.setdefault(ld, {"weight": 0.0, "holdings": []})
            x["weight"] += h["weight"]
            x["holdings"].append((h, rel))
    ranked = sorted(expo.items(), key=lambda kv: -kv[1]["weight"])
    total_linked = sum(h["weight"] for h, _ in linked)

    top = ranked[0] if ranked else None
    summary = (f'<p class="transmit"><b>連動摘要</b>你持股市值的 {total_linked * 100:.0f}% 直接連到海外龍頭；'
               + (f'連結最多的是 {e(leaders[top[0]]["name"])}（{top[1]["weight"] * 100:.0f}% 的持股市值），'
                  f'它最新一個交易日 {pct_span(leaders[top[0]]["chg_1d"])}。' if top else "")
               + "ETF 透過成分股間接連動，沒有計入。</p>")

    wmax = max((x["weight"] for _, x in ranked), default=1) or 1
    bars = "".join(
        f'<li><a class="mini" href="../supply/index.html#{e(ld)}" title="看 {e(leaders[ld]["name"])} 的供應鏈">{leader_logo(leaders[ld])}</a>'
        f'<span class="ex-name"><b>{e(leaders[ld]["name"])}</b><small>{e(leaders[ld]["market"])}・今日 {pct_span(leaders[ld]["chg_1d"])}</small></span>'
        f'<span class="ex-bar"><i style="--w:{x["weight"] / wmax * 100:.0f}%"></i></span><b class="ex-w">{x["weight"] * 100:.1f}%</b>'
        f'<span class="ex-h">{"、".join(e(h["name"]) + f"（{e(rel)}）" for h, rel in x["holdings"])}</span></li>'
        for ld, x in ranked)
    rows = "".join(
        f'<tr><td><span class="name">{stock_logo(h["code"], h["name"], t["market"], "sm")}'
        f'<span><b>{e(h["name"])}</b><small>{e(h["code"])}・占 {h["weight"] * 100:.1f}%</small></span></span></td>'
        f'<td class="num">{pct_span(t.get("chg_1d"))}</td><td><div class="revlinks">'
        + "".join(f'<span class="mini" title="{e(rel)}：{e(role)}">{leader_logo(leaders[ld])}{pct_span(leaders[ld]["chg_1d"], 1)}'
                  f'<span class="rel {REL_CLASS.get(rel, "sup")}">{e(rel)}</span></span>'
                  for ld, (rel, role, *_) in t["links"].items() if ld in leaders)
        + "</div></td></tr>" for h, t in sorted(linked, key=lambda p: -p[0]["weight"]))
    others = "、".join(f'{e(h["name"])}（{h["weight"] * 100:.1f}%）' for h, _ in unlinked)
    return (summary + f'<ul class="expo">{bars}</ul>'
            + '<div class="table-wrap"><table class="holdings"><thead><tr><th>我的持股</th><th class="num">今日</th>'
            + f'<th>連到的海外龍頭（今日漲跌）</th></tr></thead><tbody>{rows}</tbody></table></div>'
            + (f'<p class="rc-note">沒有直接連結的持股：{others}。ETF 透過成分股間接連動；個股如果你知道它的海外連結，'
               '告訴我或加進 supply_map.py 就會出現在這裡。</p>' if others else ""))
