"""
全站小圖示（取代 emoji）：いらすとや風的柔和插畫（細暖棕外框、粉彩、圓角），配科技感的簡約造型。
跟 icons.py（主題角色）、chibi.py（大佬頭像）同一套顏色與線條。
執行：python ui_icons.py → static/ui/{name}.svg；Python 用 ui()，前端用 /ui/{name}.svg。
"""

from pathlib import Path

OUT = Path(__file__).parent / "static" / "ui"
INK = "#5b4740"
RED, YELLOW, CREAM, ORANGE, BLUE, GREEN, GREY = "#ef7468", "#f9d36b", "#fff6e6", "#f5a865", "#86bfe8", "#8fd19e", "#d3cbc0"
S = f'stroke="{INK}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"'
SPARK = f'<path d="M52 8 l1.6 3.4 3.4 1.6 -3.4 1.6 -1.6 3.4 -1.6 -3.4 -3.4 -1.6 3.4 -1.6z" fill="{YELLOW}"/>'

ICONS = {
    # 鎖：投資頁需要密碼
    "lock": f'<path d="M22 28 v-6 a10 10 0 0 1 20 0 v6" fill="none" stroke="{INK}" stroke-width="5.4" stroke-linecap="round"/><path d="M22 28 v-6 a10 10 0 0 1 20 0 v6" fill="none" stroke="{GREY}" stroke-width="1.4"/>'
            f'<rect x="14" y="27" width="36" height="28" rx="7" fill="{YELLOW}" {S}/><circle cx="32" cy="39" r="3.6" fill="{INK}"/><path d="M32 41 v6" {S}/>'
            f'<circle cx="21" cy="47" r="2.4" fill="#f6a5a0" opacity=".7"/><circle cx="43" cy="47" r="2.4" fill="#f6a5a0" opacity=".7"/>' + SPARK,
    # 地圖：市場熱力圖
    "map": f'<path d="M8 16 L24 10 L40 16 L56 10 V48 L40 54 L24 48 L8 54 Z" fill="{CREAM}" {S}/><path d="M24 10 V48 M40 16 V54" {S}/>'
           f'<rect x="11" y="22" width="10" height="9" rx="2" fill="{RED}"/><rect x="27" y="30" width="10" height="10" rx="2" fill="{GREEN}"/><rect x="43" y="20" width="10" height="12" rx="2" fill="{YELLOW}"/>'
           f'<path d="M44 40 c0 -6 8 -6 8 0 c0 5 -4 9 -4 9 s-4 -4 -4 -9z" fill="{RED}" {S}/><circle cx="48" cy="40" r="1.6" fill="#fff"/>',
    # 鯨魚：大佬持股
    "whale": f'<path d="M6 36 c0 -12 12 -20 26 -20 c14 0 22 8 22 18 c0 2 4 -4 6 -8 c1 6 -1 12 -6 14 c-4 8 -14 12 -24 12 c-14 0 -24 -6 -24 -16z" fill="{BLUE}" {S}/>'
             f'<path d="M10 42 c8 8 30 10 42 2" fill="none" stroke="#fff" stroke-width="2" opacity=".7"/><ellipse cx="20" cy="33" rx="2" ry="2.6" fill="{INK}"/>'
             f'<circle cx="14" cy="38" r="2.6" fill="#f6a5a0" opacity=".75"/><path d="M28 14 c0 -5 -4 -7 -6 -9 M28 14 c0 -5 4 -7 6 -9" fill="none" stroke="{BLUE}" stroke-width="2.4" stroke-linecap="round"/>',
    # 鏈結：供應鏈
    "chain": f'<rect x="6" y="22" width="28" height="18" rx="9" fill="none" stroke="{INK}" stroke-width="6"/><rect x="6" y="22" width="28" height="18" rx="9" fill="none" stroke="{YELLOW}" stroke-width="3"/>'
             f'<rect x="30" y="24" width="28" height="18" rx="9" fill="none" stroke="{INK}" stroke-width="6"/><rect x="30" y="24" width="28" height="18" rx="9" fill="none" stroke="{RED}" stroke-width="3"/>'
             f'<circle cx="32" cy="12" r="4" fill="{GREEN}" {S}/><path d="M32 16 v5" {S}/>',
    # 上升圖表：模擬交易
    "chart": f'<rect x="8" y="10" width="48" height="44" rx="8" fill="{CREAM}" {S}/>'
             f'<rect x="15" y="36" width="7" height="12" rx="1.5" fill="{YELLOW}" {S}/><rect x="28" y="28" width="7" height="20" rx="1.5" fill="{ORANGE}" {S}/><rect x="41" y="20" width="7" height="28" rx="1.5" fill="{RED}" {S}/>'
             f'<path d="M14 30 L28 22 L36 26 L50 14" fill="none" stroke="{RED}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M44 14 h6 v6" fill="none" stroke="{RED}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>' + SPARK,
    # 盾牌：風控
    "shield": f'<path d="M32 6 L52 13 V30 c0 13 -9 22 -20 27 c-11 -5 -20 -14 -20 -27 V13 Z" fill="{BLUE}" {S}/><path d="M32 12 L46 17 V30 c0 9 -6 16 -14 20 Z" fill="#b9dbf3"/>'
              f'<path d="M23 31 l6 6 l12 -13" fill="none" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>',
    # 火箭：回測／進攻
    "rocket": f'<path d="M32 6 c10 6 14 18 12 30 H20 c-2 -12 2 -24 12 -30z" fill="{CREAM}" {S}/><circle cx="32" cy="22" r="5" fill="{BLUE}" {S}/>'
              f'<path d="M20 30 l-8 10 h9 Z M44 30 l8 10 h-9 Z" fill="{RED}" {S}/><path d="M26 36 h12 l-2 6 h-8 Z" fill="{GREY}" {S}/>'
              f'<path d="M28 44 c0 6 4 10 4 14 c0 -4 4 -8 4 -14" fill="{YELLOW}" {S}/>',
    # 報紙：新聞出處
    "news": f'<rect x="10" y="12" width="40" height="42" rx="5" fill="{CREAM}" {S}/><path d="M50 22 h6 v26 a6 6 0 0 1 -6 6" fill="{GREY}" {S}/>'
            f'<rect x="16" y="18" width="28" height="8" rx="2" fill="{RED}"/><path d="M16 32 h12 M16 38 h12 M16 44 h28 M16 49 h20" {S}/><rect x="32" y="31" width="12" height="10" rx="2" fill="{BLUE}"/>',
    # 文件：官方申報 PDF
    "doc": f'<path d="M14 6 H38 L50 18 V56 a2 2 0 0 1 -2 2 H14 a2 2 0 0 1 -2 -2 V8 a2 2 0 0 1 2 -2z" fill="{CREAM}" {S}/><path d="M38 6 V18 H50" fill="{GREY}" {S}/>'
           f'<path d="M19 28 h24 M19 35 h24 M19 42 h16" {S}/><circle cx="44" cy="48" r="7" fill="{RED}" {S}/><path d="M41 48 l2 2 l4 -4" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    # 獎盃：排行榜
    "trophy": f'<path d="M18 10 H46 V24 c0 9 -6 15 -14 15 c-8 0 -14 -6 -14 -15 Z" fill="{YELLOW}" {S}/><path d="M18 14 H10 c0 8 4 12 9 13 M46 14 H54 c0 8 -4 12 -9 13" fill="none" {S}/>'
              f'<path d="M28 39 h8 v8 h-8 Z" fill="{ORANGE}" {S}/><rect x="20" y="47" width="24" height="9" rx="2" fill="{RED}" {S}/>'
              f'<ellipse cx="27" cy="22" rx="1.8" ry="2.4" fill="{INK}"/><ellipse cx="37" cy="22" rx="1.8" ry="2.4" fill="{INK}"/><path d="M29 28 q3 3 6 0" fill="none" {S}/>' + SPARK,
    # 星星：自選（亮／暗）
    "star-on": f'<path d="M32 6 L39 22 L56 24 L43 36 L47 54 L32 45 L17 54 L21 36 L8 24 L25 22 Z" fill="{YELLOW}" {S}/>'
               f'<ellipse cx="27" cy="32" rx="1.8" ry="2.4" fill="{INK}"/><ellipse cx="37" cy="32" rx="1.8" ry="2.4" fill="{INK}"/><path d="M29 38 q3 3 6 0" fill="none" {S}/>',
    "star-off": f'<path d="M32 6 L39 22 L56 24 L43 36 L47 54 L32 45 L17 54 L21 36 L8 24 L25 22 Z" fill="#3a3a42" stroke="{GREY}" stroke-width="2.2" stroke-linejoin="round"/>',
}


def ui(name: str, prefix: str = "../", cls: str = "", alt: str = "") -> str:
    return f'<img class="ui-ico {cls}" src="{prefix}ui/{name}.svg" alt="{alt}" aria-hidden="{"false" if alt else "true"}">'


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, body in ICONS.items():
        (OUT / f"{name}.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{body}</svg>', encoding="utf-8")
    print(f"✅ {len(ICONS)} 個小圖示 → {OUT}")


if __name__ == "__main__":
    main()
