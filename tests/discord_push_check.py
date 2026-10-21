"""discord_push 的小檢查：python tests/discord_push_check.py（不連網、不需要金鑰）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.pop("GROQ_API_KEY", None)
import discord_push as dp  # noqa: E402

dp.news = lambda: []  # 不連網

data = '{"本益比":24.82,"本益比在近10年的百分位":91,"外資":-795.4,"近5日%":-7.58}'
assert dp.numbers_ok("本益比 24.8 倍、近 10 年 91% 高位", data)
assert dp.numbers_ok("外資賣超 795.4 億、費半 5 天跌 7.6%", data)
assert not dp.numbers_ok("本益比 30 倍", data)            # 資料裡沒有的數字
assert not dp.numbers_ok("跌了 7.59%", data)              # 位數比資料多也不行

fx = {"TWD=X": {"price": 32.4, "pct": -0.5}, "JPYTWD=X": {"price": 0.2029, "pct": -0.4}}
market = {"date": "2026-10-21", "summary": "台股加權收 46,888；587 漲", "valuation": {"pe": 24.82, "pct": {"pe": 91}, "median": {"pe": 16.6}}}
out = dp.lines(None, market, None, fx)                    # 沒有金鑰 → 固定句型
assert "100 日圓 20.290" in out[0] and out[1].startswith("• [台股 10-21｜台股加權收 46,888](")
assert "本益比 24.82 倍，在近 10 年 91% 的位置" in out[2]
print("ok")

us = {"indices": [{"ticker": "^GSPC", "name": "S&P 500", "date": "2026-10-20", "d1": 0.28, "d5": -1.2},
                  {"ticker": "^VIX", "name": "VIX 恐慌指數", "price": 17.31, "d1": -6.13, "d5": 13.36, "pos52": 22, "hi52": 31.05, "lo52": 13.47}]}
vix = [x for x in dp.lines(None, None, us, {}) if "市場情緒" in x]
assert vix and vix[0].startswith("• [市場情緒 VIX 17.31（-6.13%）｜近 52 週區間的 22% 位置](")
print("vix ok")

# 正負號：明寫的 +／- 要跟資料一致；沒寫正負號只比數值
d2 = '{"外資":-795.4,"漲跌%":1.28,"日期":"2026-10-21"}'
assert dp.numbers_ok("外資賣超 795.4 億", d2) and dp.numbers_ok("外資 -795.4 億", d2)
assert not dp.numbers_ok("外資 +795.4 億", d2) and not dp.numbers_ok("台股 -1.28%", d2)
assert dp.numbers_ok("10-21 台股 +1.28%", d2)               # 日期裡的「-」不是負號

# 沒有 AI 時匯率那行也有一句固定說明
fx2 = {"TWD=X": {"price": 32.4, "pct": -0.5}, "JPYTWD=X": {"price": 0.2029, "pct": -0.4}, "EURTWD=X": {"price": 36.4, "pct": 0.1}}
assert "｜台幣對美元、日圓升值，對歐元貶值](" in dp.lines(None, None, None, fx2)[0]
print("sign/fx ok")
