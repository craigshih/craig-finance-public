# Craig 財經站（公開版）

台股、美股資訊整理網站的原始碼：每日一檔、台股收盤（指數、法人、族群、市場寬度、RRG）、美股、
供應鏈地圖、大佬 13F 持股、模擬交易、AI 投資顧問與選股機器人。部署在 Cloudflare Pages（靜態頁 + Pages Functions + D1）。

這份是「公開版」：拿掉了站長個人的持股、交易紀錄與對帳功能（`portfolio.py` 換成空殼），其餘程式都在。

## 直接拿資料（最簡單）

不想自己建站的話，正式站有公開 JSON（每天收盤後、早上 9 點左右更新）：

| 網址 | 內容 |
|---|---|
| `https://craig-finance.pages.dev/feed/index.json` | 說明與免責聲明 |
| `https://craig-finance.pages.dev/feed/daily-pick.json` | 今日的每日一檔；`text` 是排好版的純文字，每則都在 Discord 2000 字上限內 |
| `https://craig-finance.pages.dev/feed/daily-pick-archive.json` | 最近 60 天的每日一檔清單 |
| `https://craig-finance.pages.dev/feed/market.json` | 台股收盤：`summary` 一句話總結，加上指數、三大法人、族群、強勢股、注意處置股、除權息、估值、期貨籌碼 |
| `https://craig-finance.pages.dev/feed/us.json` | 美股指數、類股 ETF、權值股、SEC 最新申報 |

Discord 範例（discord.py，每天 9:10 把每日一檔貼到頻道）：

```python
import aiohttp, discord
from discord.ext import tasks
from datetime import time, timezone, timedelta

CHANNEL_ID = 123456789  # 你的頻道
client = discord.Client(intents=discord.Intents.default())

@tasks.loop(time=time(9, 10, tzinfo=timezone(timedelta(hours=8))))
async def daily_pick():
    async with aiohttp.ClientSession() as s:
        d = await (await s.get("https://craig-finance.pages.dev/feed/daily-pick.json")).json()
    ch = client.get_channel(CHANNEL_ID)
    for msg in d["text"]:
        await ch.send(msg)

@client.event
async def on_ready():
    daily_pick.start()

client.run("你的 bot token")
```

## 自己建一份

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python market.py && .venv/bin/python us.py      # 抓資料（其他資料腳本見 .github/workflows/build.yml）
.venv/bin/python build.py                                # 輸出到 site/
npm install && npx wrangler pages dev site               # 本機預覽（含 Functions）
```

- 部署流程在 `.github/workflows/`，需要的 secrets：`CLOUDFLARE_API_TOKEN`、`GROQ_API_KEY`（AI 文字）、`SESSION_SECRET`、
  `PORTFOLIO_PASSWORD`（顧問頁密碼）；每日一檔寄信另需 `GMAIL_USER`、`GMAIL_APP_PASSWORD`、`MAIL_TO`，LINE 推播需 `LINE_CHANNEL_SECRET`、`LINE_CHANNEL_ACCESS_TOKEN`。
- workflow 裡 checkout `craigshih/Tim-Lu`（每日總經）與 `craigshih/investment-team`（每週研究）兩個私人 repo，沒有權限時那兩區會是空的，其他照常。
- `build.yml` 產生 wrangler.toml 的地方，`ACCESS_TEAM_DOMAIN`、`ACCESS_AUD` 要換成你自己的 Cloudflare Access 設定。
- 測試：`node --test tests/*.test.js`。

## 資料來源與聲明

證交所、櫃買中心、期交所 OpenAPI，Yahoo Finance、SEC EDGAR、維基百科、鉅亨網。不爬取 robots.txt 禁止的網站。
AI 產生的文字僅供學習研究，不構成投資建議。
