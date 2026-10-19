"""
四位投資人的素描風格頭像（SVG）。依公開照片的外型特徵重新繪製的原創插畫，不是照片描摹，也不是寫實肖像。
鉛筆質感：feTurbulence + feDisplacementMap 讓線條微微抖動；底下一層淡淡的水彩色塊，上面疊排線陰影。
執行：python portraits.py → static/portraits/{id}.svg
"""
import re
from pathlib import Path

OUT = Path(__file__).parent / "static" / "portraits"

DEFS = """<defs>
  <filter id="pencil" x="-5%" y="-5%" width="110%" height="110%">
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="{seed}" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="2" xChannelSelector="R" yChannelSelector="G"/>
  </filter>
  <filter id="wash" x="-10%" y="-10%" width="120%" height="120%">
    <feTurbulence type="fractalNoise" baseFrequency="0.05" numOctaves="2" seed="{seed}" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="5"/>
  </filter>
  <pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
    <line x1="0" y1="0" x2="0" y2="5" stroke="#3a3f47" stroke-width="0.7" opacity="0.5"/>
  </pattern>
  <pattern id="hair" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(65)">
    <line x1="0" y1="0" x2="0" y2="3" stroke="#22252b" stroke-width="1.2" opacity="0.8"/>
  </pattern>
  <pattern id="dots" width="9" height="9" patternUnits="userSpaceOnUse">
    <rect x="3" y="3" width="2.4" height="2.4" fill="#9aa3b5"/>
  </pattern>
  <pattern id="stripe" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(-35)">
    <line x1="0" y1="0" x2="0" y2="7" stroke="#e8d3b0" stroke-width="1.4"/>
  </pattern>
</defs>"""

L = 'fill="none" stroke="#2b2f36" stroke-linecap="round" stroke-linejoin="round"'
SKIN = "#f2d9c2"


def svg(seed: int, bg: str, wash: str, lines: str) -> str:
    """wash：水彩色塊（半透明、邊緣微暈）；lines：鉛筆線條。"""
    lines = re.sub(r'(<[^>]*fill="url\(#\w+\)"[^>]*?) fill="none"', r"\1", lines)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 240" role="img">{DEFS.format(seed=seed)}'
            f'<rect width="200" height="240" fill="{bg}"/>'
            f'<g filter="url(#wash)" opacity=".75">{wash}</g>'
            f'<g filter="url(#pencil)">{lines}</g></svg>')


def suit(jacket: str, shirt: str = "#ffffff", tie: str | None = None, tie_pattern: str = "") -> tuple[str, str]:
    """西裝、襯衫與領帶：回傳 (色塊, 線條)。tie=None 代表開領不打領帶。"""
    wash = (f'<path d="M24 240 C34 204 58 190 82 184 L100 216 L118 184 C142 190 166 204 176 240 Z" fill="{jacket}"/>'
            f'<path d="M82 184 L100 216 L118 184 L112 180 L100 190 L88 180 Z" fill="{shirt}"/>')
    lines = (f'<path d="M24 240 C34 204 58 190 82 184 M118 184 C142 190 166 204 176 240" {L} stroke-width="2"/>'
             f'<path d="M82 184 L96 236 M118 184 L104 236" {L} stroke-width="1.5"/>'
             f'<path d="M88 180 L100 192 L112 180" {L} stroke-width="1.4"/>')
    if tie:
        shape = "M95 194 L100 190 L105 194 L103 200 L108 236 L92 236 L97 200 Z"
        wash += f'<path d="{shape}" fill="{tie}"/>'
        if tie_pattern:
            wash += f'<path d="{shape}" fill="url(#{tie_pattern})"/>'
        lines += f'<path d="M95 194 L100 190 L105 194 L103 200 L108 236 M97 200 L92 236 M97 200 L103 200" {L} stroke-width="1.3"/>'
    else:
        lines += f'<path d="M88 180 L94 202 L100 192 L106 202 L112 180" {L} stroke-width="1.4"/>'
    return wash, lines


def grin(y: int, w: int = 20) -> str:
    """露齒笑：上唇弧、下唇弧、牙齒線。"""
    return (f'<path d="M{100 - w} {y} C{100 - w / 2} {y + 7} {100 + w / 2} {y + 7} {100 + w} {y}" {L} stroke-width="2"/>'
            f'<path d="M{100 - w + 2} {y + 1} C{100 - w / 2} {y + 18} {100 + w / 2} {y + 18} {100 + w - 2} {y + 1}" {L} stroke-width="1.8"/>'
            f'<path d="M{100 - w + 4} {y + 4} C{100 - w / 2} {y + 9} {100 + w / 2} {y + 9} {100 + w - 4} {y + 4}" {L} stroke-width=".9" opacity=".7"/>')


def grin_wash(y: int, w: int = 20) -> str:
    return (f'<path d="M{100 - w + 2} {y + 1} C{100 - w / 2} {y + 18} {100 + w / 2} {y + 18} {100 + w - 2} {y + 1} '
            f'C{100 + w / 2} {y + 7} {100 - w / 2} {y + 7} {100 - w + 2} {y + 1} Z" fill="#ffffff"/>')


# ---------- 段永平：圓臉、黑色短髮、瞇眼大笑、西裝深色點點領帶 ----------
w, l = suit("#3b3f48", tie="#2d3550", tie_pattern="dots")
DUAN = svg(11, "#e9eff8", f'''
<path d="M58 100 C56 138 72 170 100 176 C128 170 144 138 142 100 C142 70 124 56 100 56 C76 56 58 70 58 100 Z" fill="{SKIN}"/>
<path d="M60 100 C56 66 74 44 100 44 C126 44 144 66 140 100 C136 82 126 72 100 72 C74 72 64 82 60 100 Z" fill="#2a2a2e"/>
{grin_wash(142, 22)}{w}''', f'''
<path d="M58 100 C56 138 72 170 100 176 C128 170 144 138 142 100" {L} stroke-width="2.2"/>
<path d="M60 100 C56 66 74 44 100 44 C126 44 144 66 140 100" {L} stroke-width="2.2"/>
<path d="M60 100 C64 84 74 74 100 72 C126 74 136 84 140 100 C140 70 124 48 100 48 C76 48 60 70 60 100 Z" fill="url(#hair)" {L} stroke-width="1.6"/>
<path d="M58 104 C48 102 48 124 58 128 M142 104 C152 102 152 124 142 128" {L} stroke-width="1.9"/>
<path d="M70 96 C78 91 88 91 93 94 M107 94 C112 91 122 91 130 96" {L} stroke-width="2.6"/>
<path d="M72 108 C78 102 86 102 92 108 M108 108 C114 102 122 102 128 108" {L} stroke-width="2.2"/>
<path d="M68 112 L64 116 M70 114 L67 119 M132 112 L136 116 M130 114 L133 119" {L} stroke-width="1" opacity=".7"/>
<path d="M100 110 C99 120 93 128 95 133 C98 136 102 136 106 133 C108 129 104 126 103 122" {L} stroke-width="1.7"/>
<path d="M76 132 C72 140 74 150 80 156 M124 132 C128 140 126 150 120 156" {L} stroke-width="1.3" opacity=".75"/>
<path d="M64 124 C68 146 80 162 94 170" fill="url(#hatch)" stroke="none" opacity=".5"/>
{grin(142, 22)}{l}''')

# ---------- 巴菲特：往後梳的蓬鬆白髮、細金屬框眼鏡、露齒笑、紅領帶 ----------
w, l = suit("#2c2f36", tie="#c0392b", tie_pattern="dots")
BUFFETT = svg(3, "#eef4ec", f'''
<path d="M58 98 C56 136 66 164 86 176 C94 181 106 181 114 176 C134 164 144 136 142 98 C142 70 124 58 100 58 C76 58 58 70 58 98 Z" fill="{SKIN}"/>
<path d="M52 108 C42 70 60 30 100 28 C142 30 158 70 148 108 C146 90 140 70 104 60 C70 60 56 84 52 108 Z" fill="#e9e9ec"/>
{grin_wash(148, 21)}{w}''', f'''
<path d="M58 98 C56 136 66 164 86 176 C94 181 106 181 114 176 C134 164 144 136 142 98" {L} stroke-width="2.2"/>
<path d="M52 108 C42 70 60 30 100 28 C142 30 158 70 148 108" {L} stroke-width="2"/>
<path d="M58 92 C62 70 80 60 104 60 C126 60 140 72 142 92" {L} stroke-width="1.6"/>
<path d="M66 70 C82 46 120 40 140 62 M72 60 C90 40 124 38 144 70 M62 82 C70 58 96 50 118 54" {L} stroke-width="1" opacity=".55"/>
<path d="M56 106 C46 104 46 126 56 130 M144 106 C154 104 154 126 144 130" {L} stroke-width="1.9"/>
<path d="M68 92 C76 86 88 86 94 91 M106 91 C112 86 124 86 132 92" {L} stroke-width="3.4"/>
<path d="M76 74 C90 70 110 70 124 74 M80 80 C92 77 108 77 120 80" {L} stroke-width=".9" opacity=".55"/>
<path d="M66 99 C66 96 69 94 74 94 L92 94 C96 94 97 97 97 100 L96 112 C95 117 92 119 86 119 L76 119 C70 119 67 116 66 111 Z" {L} stroke-width="1.2"/>
<path d="M103 100 C103 97 104 94 108 94 L126 94 C131 94 134 96 134 99 L134 111 C133 116 130 119 124 119 L114 119 C108 119 105 117 104 112 Z" {L} stroke-width="1.2"/>
<path d="M97 101 C99 99 101 99 103 101 M66 100 L57 98 M134 100 L143 98" {L} stroke-width="1.1"/>
<path d="M74 108 C79 103 86 103 90 108 M110 108 C114 103 121 103 126 108" {L} stroke-width="1.9"/>
<path d="M100 112 C98 124 93 132 95 137 C98 141 103 141 108 137 C110 133 106 129 104 126" {L} stroke-width="1.8"/>
<path d="M74 130 C68 142 70 154 78 162 M126 130 C132 142 130 154 122 162" {L} stroke-width="1.4" opacity=".8"/>
<path d="M66 122 C70 148 82 166 96 174" fill="url(#hatch)" stroke="none" opacity=".5"/>
{grin(148, 21)}{l}''')

# ---------- 芒格：側分灰白髮、粗的玳瑁色方框眼鏡、抿嘴淺笑、酒紅條紋領帶 ----------
w, l = suit("#2a2c33", tie="#7a2e2e", tie_pattern="stripe")
MUNGER = svg(7, "#f6efe3", f'''
<path d="M62 94 C60 134 68 166 88 178 C95 182 105 182 112 178 C132 166 140 134 138 94 C138 66 122 54 100 54 C78 54 62 66 62 94 Z" fill="{SKIN}"/>
<path d="M60 98 C54 62 74 38 102 38 C130 38 146 62 140 98 C138 80 132 68 120 62 C100 58 80 62 66 74 C62 82 61 90 60 98 Z" fill="#d6d6d9"/>
<rect x="66" y="94" width="31" height="24" rx="4" fill="#cfe0e8" opacity=".55"/><rect x="103" y="94" width="31" height="24" rx="4" fill="#cfe0e8" opacity=".55"/>
{w}''', f'''
<path d="M62 94 C60 134 68 166 88 178 C95 182 105 182 112 178 C132 166 140 134 138 94" {L} stroke-width="2.2"/>
<path d="M60 98 C54 62 74 38 102 38 C130 38 146 62 140 98" {L} stroke-width="2"/>
<path d="M66 74 C80 62 100 58 120 62 C132 68 138 80 140 98" {L} stroke-width="1.5"/>
<path d="M84 42 C84 50 82 58 78 66 M88 44 C104 46 122 52 134 66 M86 50 C102 52 118 58 130 70 M84 58 C98 58 112 62 124 70" {L} stroke-width="1" opacity=".6"/>
<path d="M60 102 C50 100 50 120 60 124 M140 102 C150 100 150 120 140 124" {L} stroke-width="1.9"/>
<rect x="66" y="94" width="31" height="24" rx="4" fill="none" stroke="#6b4426" stroke-width="5"/>
<rect x="103" y="94" width="31" height="24" rx="4" fill="none" stroke="#6b4426" stroke-width="5"/>
<path d="M97 102 L103 102 M66 99 L58 97 M134 99 L142 97" stroke="#6b4426" stroke-width="4" stroke-linecap="round"/>
<path d="M70 88 C78 85 88 85 94 88 M106 88 C112 85 122 85 130 88" {L} stroke-width="2.4"/>
<path d="M76 107 C80 104 86 104 89 107 M111 107 C114 104 120 104 124 107" {L} stroke-width="1.8"/>
<circle cx="82.5" cy="107.5" r="1.8" fill="#2b2f36"/><circle cx="117.5" cy="107.5" r="1.8" fill="#2b2f36"/>
<path d="M100 116 C98 128 94 136 96 141 C99 144 104 144 108 141 C110 137 106 134 104 130" {L} stroke-width="1.7"/>
<path d="M84 156 C92 160 106 160 117 153" {L} stroke-width="2"/>
<path d="M78 140 C74 150 76 160 82 166 M122 138 C126 148 124 158 118 164" {L} stroke-width="1.3" opacity=".8"/>
<path d="M66 118 C68 146 78 166 92 176" fill="url(#hatch)" stroke="none" opacity=".55"/>
{l}''')

# ---------- 李錄：不戴眼鏡、往上梳的短髮兩鬢斑白、微笑、藍色西裝外套開領 ----------
w, l = suit("#2f4b8a", shirt="#ffffff", tie=None)
LILU = svg(17, "#f1ecf7", f'''
<path d="M62 98 C60 136 72 166 92 177 C97 180 103 180 108 177 C128 166 140 136 138 98 C138 70 122 58 100 58 C78 58 62 70 62 98 Z" fill="{SKIN}"/>
<path d="M60 100 C54 62 76 40 102 40 C128 40 146 62 140 100 C136 84 130 72 116 66 C102 70 84 70 72 78 C66 84 62 92 60 100 Z" fill="#33353b"/>
<path d="M60 100 C58 90 60 82 64 78 L66 98 Z M140 100 C142 90 140 82 136 78 L134 98 Z" fill="#9b9ea6"/>
{grin_wash(148, 16)}{w}''', f'''
<path d="M62 98 C60 136 72 166 92 177 C97 180 103 180 108 177 C128 166 140 136 138 98" {L} stroke-width="2.2"/>
<path d="M60 100 C54 62 76 40 102 40 C128 40 146 62 140 100" {L} stroke-width="2"/>
<path d="M60 100 C54 62 76 40 102 40 C128 40 146 62 140 100 C136 84 130 72 116 66 C102 70 84 70 72 78 C66 84 62 92 60 100 Z" fill="url(#hair)" {L} stroke-width="1.4"/>
<path d="M76 70 C88 52 110 46 126 54 M84 64 C96 50 116 46 132 60" {L} stroke-width="1.1" opacity=".6"/>
<path d="M62 104 C52 102 52 122 62 126 M138 104 C148 102 148 122 138 126" {L} stroke-width="1.9"/>
<path d="M72 96 C79 92 87 92 93 95 M107 95 C113 92 121 92 128 96" {L} stroke-width="2.4"/>
<path d="M74 108 C78 104 86 104 90 108 C86 110 78 110 74 108 Z M110 108 C114 104 122 104 126 108 C122 110 114 110 110 108 Z" {L} stroke-width="1.6"/>
<circle cx="82" cy="107.5" r="2.2" fill="#2b2f36"/><circle cx="118" cy="107.5" r="2.2" fill="#2b2f36"/>
<path d="M100 112 C98 122 95 130 97 134 C100 137 104 137 107 134" {L} stroke-width="1.7"/>
<path d="M80 136 C76 144 78 152 84 158 M120 136 C124 144 122 152 116 158" {L} stroke-width="1.2" opacity=".7"/>
<path d="M66 122 C68 146 78 164 92 174" fill="url(#hatch)" stroke="none" opacity=".45"/>
{grin(148, 16)}
<path d="M120 196 L120 214" stroke="#2b2f36" stroke-width="1.2" opacity=".6"/><circle cx="120" cy="196" r="2" fill="#2b2f36" opacity=".7"/>
{l}''')

PORTRAITS = {"duan": DUAN, "buffett": BUFFETT, "munger": MUNGER, "lilu": LILU}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for key, s in PORTRAITS.items():
        (OUT / f"{key}.svg").write_text(s, encoding="utf-8")
    print("✅", ", ".join(PORTRAITS))
