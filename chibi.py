"""
Q 版大佬頭像（全站統一風格）：いらすとや風的柔和插畫（細暖棕外框、粉彩、豆豆眼、圓腮紅），
放在黑底＋紅黃漸層細框的「科技感」頭像框裡；跟每日總經的主題圖示同一套畫法。
依公開照片上最好認的外型特徵（髮型、眼鏡、領帶）畫的原創卡通，不是照片描摹、也不是寫實肖像。
執行：python chibi.py → static/portraits/q/{id}.svg
"""

from pathlib import Path

OUT = Path(__file__).parent / "static" / "portraits" / "q"
INK = "#5b4740"   # いらすとや風：細的暖棕色外框
SKIN = "#fde3cf"
S = f'stroke="{INK}" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"'

# 頭：中心 (60, 56)，半徑 30
HEAD = f'<ellipse cx="60" cy="56" rx="30" ry="29" fill="{SKIN}" {S}/>'
EARS = f'<ellipse cx="30" cy="60" rx="5" ry="7" fill="{SKIN}" {S}/><ellipse cx="90" cy="60" rx="5" ry="7" fill="{SKIN}" {S}/>'


def eyes(kind: str = "dot") -> str:
    if kind == "squint":  # 瞇眼大笑 ^^
        return (f'<path d="M45 58 q4.5 -5 9 0" fill="none" {S}/><path d="M66 58 q4.5 -5 9 0" fill="none" {S}/>')
    return "".join(f'<ellipse cx="{x}" cy="58" rx="2.4" ry="3.1" fill="{INK}"/>' for x in (49, 71))


def mouth(kind: str = "smile") -> str:
    if kind == "grin":  # 露齒笑
        return f'<path d="M52 68.5 Q60 77 68 68.5 Z" fill="#fff" {S}/>'
    if kind == "laugh":
        return f'<path d="M51 67.5 Q60 79 69 67.5 Z" fill="#ef7468" {S}/>'
    if kind == "closed":
        return f'<path d="M55 70.5 Q60 73 65 70.5" fill="none" {S}/>'
    return f'<path d="M54 69 Q60 74 66 69" fill="none" {S}/>'


BLUSH = '<circle cx="41" cy="66" r="4.2" fill="#f6a5a0" opacity=".75"/><circle cx="79" cy="66" r="4.2" fill="#f6a5a0" opacity=".75"/>'


def glasses(kind: str, color: str = INK) -> str:
    if kind == "round":
        return (f'<circle cx="49" cy="58" r="8" fill="#ffffff22" stroke="{color}" stroke-width="1.8"/>'
                f'<circle cx="71" cy="58" r="8" fill="#ffffff22" stroke="{color}" stroke-width="1.8"/><path d="M57 58 h6" stroke="{color}" stroke-width="1.8"/>')
    if kind == "square":
        return (f'<rect x="39" y="51" width="19" height="14" rx="3" fill="#ffffff22" stroke="{color}" stroke-width="2.5"/>'
                f'<rect x="62" y="51" width="19" height="14" rx="3" fill="#ffffff22" stroke="{color}" stroke-width="2.5"/><path d="M58 57 h4" stroke="{color}" stroke-width="2.2"/>')
    if kind == "rect":
        return (f'<rect x="40" y="52" width="18" height="12" rx="4" fill="#ffffff22" stroke="{color}" stroke-width="1.8"/>'
                f'<rect x="62" y="52" width="18" height="12" rx="4" fill="#ffffff22" stroke="{color}" stroke-width="1.8"/><path d="M58 57 h4" stroke="{color}" stroke-width="1.8"/>')
    return ""


def body(jacket: str, shirt: str = "#ffffff", tie: str | None = None, extra: str = "") -> str:
    """肩膀與上身（下方被圓形背景切掉）。"""
    out = f'<path d="M22 120 Q22 92 46 88 L74 88 Q98 92 98 120 Z" fill="{jacket}" {S}/>'
    out += f'<path d="M48 88 L60 104 L72 88 Z" fill="{shirt}" {S}/>'
    if tie:
        out += f'<path d="M57 92 L63 92 L65 112 L60 118 L55 112 Z" fill="{tie}" {S}/>'
    out += f'<path d="M48 88 L56 100 M72 88 L64 100" fill="none" {S}/>'
    return out + extra


def svg(bg: str, parts: str, title: str) -> str:
    """科技感頭像框：黑底、人物代表色的柔光、紅→黃漸層細框。"""
    uid = abs(hash(title)) % 10_000
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" role="img" aria-label="{title}"><title>{title}</title>'
            f'<defs><clipPath id="c{uid}"><circle cx="60" cy="60" r="56"/></clipPath>'
            f'<radialGradient id="g{uid}" cx="50%" cy="38%" r="65%"><stop offset="0" stop-color="{bg}" stop-opacity=".55"/><stop offset="1" stop-color="#141418"/></radialGradient>'
            f'<linearGradient id="r{uid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e3232c"/><stop offset="1" stop-color="#ffc928"/></linearGradient></defs>'
            f'<circle cx="60" cy="60" r="56" fill="url(#g{uid})"/>'
            + "".join(f'<circle cx="{x}" cy="{y}" r="0.9" fill="#ffffff" opacity=".18"/>' for x in range(18, 104, 12) for y in range(18, 60, 12))
            + f'<g clip-path="url(#c{uid})">{parts}</g>'
            f'<circle cx="60" cy="60" r="57" fill="none" stroke="url(#r{uid})" stroke-width="2.6"/></svg>')


def face(hair_back: str, hair_front: str, e: str = "dot", m: str = "smile", g: str = "", gcolor: str = INK, extra: str = "") -> str:
    return hair_back + EARS + HEAD + BLUSH + eyes(e) + mouth(m) + glasses(g, gcolor) + hair_front + extra


PEOPLE = {
    # 段永平：圓臉、黑色短髮、瞇眼大笑、深色西裝點點領帶
    "duan": ("#2563eb", "段永平",
             body("#4b5268", tie="#6d7fa8", extra='<circle cx="59" cy="99" r="1.3" fill="#c9d4f0"/><circle cx="62" cy="106" r="1.3" fill="#c9d4f0"/>')
             + face("", f'<path d="M30 56 Q28 24 60 24 Q92 24 90 56 Q86 40 70 36 Q58 42 44 38 Q34 42 30 56 Z" fill="#4a3b36" {S}/>', "squint", "laugh")),
    # 巴菲特：往後梳的蓬鬆白髮、細金屬框眼鏡、露齒笑、紅領帶
    "buffett": ("#e3232c", "巴菲特",
                body("#59617a", tie="#e8665c")
                + face(f'<path d="M26 60 Q20 30 40 22 Q48 12 62 16 Q78 10 86 22 Q100 28 94 60 Z" fill="#fafafa" {S}/>',
                       f'<path d="M32 46 Q38 28 60 27 Q82 28 88 46 Q80 36 60 36 Q42 36 32 46 Z" fill="#fafafa" {S}/>',
                       "dot", "grin", "round", "#9a8a6a")),
    # 芒格：側分灰白髮、粗的玳瑁色方框眼鏡、抿嘴淺笑、酒紅條紋領帶
    "munger": ("#7c3aed", "芒格",
               body("#4f5568", tie="#b2565f", extra=f'<path d="M57 98 L63 95 M56 105 L64 101 M57 111 L63 108" stroke="#d9a0a8" stroke-width="1.2"/>')
               + face(f'<path d="M28 58 Q26 34 40 28 L40 58 Z M92 58 Q94 34 80 28 L80 58 Z" fill="#e3e3e3" {S}/>',
                      f'<path d="M32 44 Q36 26 58 26 Q84 26 88 42 Q74 32 50 34 Q40 36 32 44 Z" fill="#e3e3e3" {S}/><path d="M50 27 Q52 31 50 35" fill="none" stroke="#9a9a9a" stroke-width="1.5"/>',
                      "dot", "closed", "square", "#7a4a1e")),
    # 李錄：不戴眼鏡、往上梳的短髮兩鬢斑白、微笑、藍色西裝外套開領
    "lilu": ("#0ea5a4", "李錄",
             body("#5d8ccf", shirt="#eef3fb")
             + face("", f'<path d="M30 54 Q28 30 44 24 Q52 16 62 20 Q70 14 78 22 Q92 28 90 54 Q86 40 72 36 Q60 34 48 36 Q36 40 30 54 Z" fill="#4a3b36" {S}/>'
                        f'<path d="M30 54 Q30 46 34 42 L36 56 Z M90 54 Q90 46 86 42 L84 56 Z" fill="#d0d0d0"/>', "dot", "smile")),
    # Bill Ackman：銀灰色濃密往後梳的頭髮、不戴眼鏡、深藍西裝淺藍領帶
    "ackman": ("#1d4ed8", "Bill Ackman",
               body("#46557a", tie="#7fb2e6")
               + face(f'<path d="M27 58 Q22 30 44 22 Q60 14 78 20 Q98 28 93 58 Z" fill="#d6d9de" {S}/>',
                      f'<path d="M31 46 Q36 24 62 24 Q86 26 89 44 Q80 32 62 32 Q44 32 31 46 Z" fill="#d6d9de" {S}/><path d="M44 28 Q60 26 76 30" fill="none" stroke="#9aa0a8" stroke-width="1.5"/>',
                      "dot", "smile")),
    # Stanley Druckenmiller：灰髮、頭頂稀疏、灰色西裝開領
    "druck": ("#0f766e", "Stanley Druckenmiller",
              body("#8a909e", shirt="#f2f2f2")
              + face(f'<path d="M28 60 Q26 40 34 34 L36 60 Z M92 60 Q94 40 86 34 L84 60 Z" fill="#c3c6cc" {S}/>',
                     f'<path d="M44 30 Q60 24 76 30 Q66 30 60 33 Q54 30 44 30 Z" fill="#c3c6cc" stroke="{INK}" stroke-width="1.5"/>', "dot", "smile")),
    # David Tepper：光頭、開領藍襯衫
    "tepper": ("#b45309", "David Tepper",
               body("#7fb3e3", shirt="#7fb3e3")
               + face(f'<path d="M29 62 Q28 48 33 44 L35 62 Z M91 62 Q92 48 87 44 L85 62 Z" fill="#a89c90" {S}/>',
                      '<path d="M44 34 Q52 29 62 30" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" opacity=".7"/>', "dot", "grin")),
    # Cathie Wood：金色及下巴的鮑伯頭、黑色外套、珍珠項鍊
    "wood": ("#db2777", "Cathie Wood",
             body("#4a3b36", shirt="#4a3b36", extra="".join(f'<circle cx="{x}" cy="{y}" r="2.2" fill="#fff" stroke="{INK}" stroke-width="0.8"/>'
                                                             for x, y in ((50, 92), (55, 96), (60, 97), (65, 96), (70, 92))))
             + face(f'<path d="M24 82 Q16 40 34 26 Q60 8 86 26 Q104 40 96 82 Q90 86 86 80 L86 56 L34 56 L34 80 Q30 86 24 82 Z" fill="#f6d98a" {S}/>',
                    f'<path d="M30 52 Q32 26 60 24 Q88 26 90 52 Q76 40 70 34 Q58 44 30 52 Z" fill="#f6d98a" {S}/>', "dot", "smile")),
    # Michael Burry：深色短髮、方框眼鏡、灰色 T 恤
    "burry": ("#475569", "Michael Burry",
              f'<path d="M22 120 Q22 92 46 88 L74 88 Q98 92 98 120 Z" fill="#9aa1ad" {S}/><path d="M50 88 Q60 96 70 88" fill="none" {S}/>'
              + face("", f'<path d="M30 54 Q28 26 52 22 Q70 18 84 28 Q94 38 90 54 Q86 42 76 38 L72 32 L66 38 L58 32 L52 38 Q38 40 30 54 Z" fill="#5e4a3f" {S}/>',
                     "dot", "closed", "rect")),
    # 比爾蓋茲：側分棕灰髮、方框眼鏡、V 領毛衣
    "gates": ("#059669", "比爾蓋茲",
              f'<path d="M22 120 Q22 92 46 88 L74 88 Q98 92 98 120 Z" fill="#7d9cc4" {S}/><path d="M46 88 L60 108 L74 88" fill="#ffffff" {S}/><path d="M54 92 L60 102 L66 92" fill="#9fc0e6" stroke="none"/>'
              + face(f'<path d="M28 58 Q26 36 36 30 L38 58 Z M92 58 Q94 36 84 30 L82 58 Z" fill="#a98a6c" {S}/>',
                     f'<path d="M31 50 Q32 26 60 25 Q88 26 89 48 Q76 34 56 36 Q40 38 31 50 Z" fill="#a98a6c" {S}/><path d="M40 33 Q48 30 52 36" fill="none" stroke="#5e4a38" stroke-width="1.5"/>',
                     "dot", "smile", "rect")),
    # 川普：金色往前蓬起的招牌髮型、深藍西裝、長紅領帶
    "trump": ("#b91c1c", "川普",
              body("#46557a", tie="#e8665c")
              + face(f'<path d="M27 60 Q22 36 34 28 L36 60 Z M93 60 Q98 36 86 28 L84 60 Z" fill="#f4cf6e" {S}/>',
                     f'<path d="M28 46 Q26 22 56 20 Q90 18 94 40 Q84 30 70 33 Q76 38 74 42 Q60 34 44 38 Q34 40 28 46 Z" fill="#f4cf6e" {S}/>'
                     f'<path d="M50 26 Q66 22 82 28" fill="none" stroke="#c99a2e" stroke-width="1.5"/>', "dot", "closed")),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for pid, (bg, name, parts) in PEOPLE.items():
        (OUT / f"{pid}.svg").write_text(svg(bg, parts, f"{name}（Q 版插畫）"), encoding="utf-8")
    print(f"✅ {len(PEOPLE)} 張 Q 版頭像 → {OUT}")


if __name__ == "__main__":
    main()
