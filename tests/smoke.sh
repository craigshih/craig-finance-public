#!/bin/bash
# 部署前的冒煙測試：用 wrangler pages dev 在 CI 裡跑一份完整的網站（本機 D1、真實報價），
# 模擬兩個登入的使用者實際下單，並測投資頁密碼鎖。任何一步失敗就不部署。
set -euo pipefail
BASE=http://localhost:8788
fail() { echo "❌ $*"; exit 1; }
need() { echo "$1" | grep -q "$2" || fail "$3（回應：$(echo "$1" | head -c 300)）"; }
post() { curl -s -X POST -H "Content-Type: application/json" -d "$2" "$BASE$1"; }

# 投資頁：沒登入 → 密碼頁、不能有持股內容
code=$(curl -s -o /tmp/pf.html -w '%{http_code}' "$BASE/portfolio/")
[ "$code" = 401 ] || fail "投資頁沒密碼應該回 401，實際 $code"
grep -q "這一頁需要密碼" /tmp/pf.html || fail "投資頁沒有顯示密碼頁"
grep -q "持股明細" /tmp/pf.html && fail "沒登入就看得到持股內容"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -d "password=wrong" "$BASE/portfolio/__login")
[ "$code" = 401 ] || fail "錯誤密碼應該回 401，實際 $code"
cookie=$(curl -s -D - -o /dev/null -X POST --data-urlencode "password=$SMOKE_PASSWORD" "$BASE/portfolio/__login" | grep -i '^set-cookie:' | sed 's/^[^:]*: //; s/;.*//' | tr -d '\r')
[ -n "$cookie" ] || fail "正確密碼沒有拿到 cookie"
code=$(curl -s -o /tmp/pf.html -w '%{http_code}' -H "Cookie: $cookie" "$BASE/portfolio/")
[ "$code" = 200 ] || fail "帶 cookie 應該看得到投資頁，實際 $code"
grep -q "這一頁需要密碼" /tmp/pf.html && fail "帶 cookie 還是顯示密碼頁"
echo "✅ 投資頁密碼鎖"

# AI 投資顧問：沒登入拿不到頁面、資料與 API；登入後頁面正常、API 會檢查輸入（CI 沒有 AI 金鑰 → 503）
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/portfolio/advisor/"); [ "$code" = 401 ] || fail "顧問頁沒密碼應該回 401，實際 $code"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/portfolio/advisor/holdings.json"); [ "$code" = 401 ] || fail "持股權重沒密碼應該回 401，實際 $code"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/portfolio/advisor/stocks.json"); [ "$code" = 401 ] || fail "顧問資料沒密碼應該回 401，實際 $code"
r=$(curl -s -X POST -H "Content-Type: application/json" -d '{"question":"台積電"}' "$BASE/portfolio/api/advisor"); need "$r" '請重新輸入密碼' "沒登入不能問顧問"
code=$(curl -s -o /tmp/adv.html -w '%{http_code}' -H "Cookie: $cookie" "$BASE/portfolio/advisor/"); [ "$code" = 200 ] || fail "登入後顧問頁應該 200，實際 $code"
grep -q "問顧問" /tmp/adv.html || fail "顧問頁內容不對"
apost() { curl -s -X POST -H "Cookie: $cookie" -H "Content-Type: application/json" -d "$1" "$BASE/portfolio/api/advisor"; }
need "$(apost '{"question":""}')" '請輸入問題' "空白問題應該擋下"
r=$(apost '{"question":"台積電和聯電哪個比較好？"}')
if [ -f site/portfolio/advisor/stocks.json ]; then
  need "$r" 'AI 金鑰還沒設定' "沒有金鑰時應該回清楚的錯誤"
  need "$r" '"found":\["2330","2303"\]' "應該從問題找出台積電與聯電（也代表讀得到顧問資料）"
else
  need "$r" '顧問資料還沒產生' "沒有顧問資料時應該回清楚的錯誤"
fi
echo "✅ AI 投資顧問"

# 專屬投資顧問（訪客版）：不用密碼直接用；但開不了投資頁，資料也不含只因站長持股才計算的股票
code=$(curl -s -o /tmp/rb.html -w '%{http_code}' "$BASE/robot/"); [ "$code" = 200 ] || fail "專屬投資顧問應該直接打得開，實際 $code"
grep -q "/robot/api/advisor" /tmp/rb.html || fail "專屬投資顧問應該打訪客版 API"
grep -q "免責聲明" /tmp/rb.html || fail "專屬投資顧問頁要有免責聲明"
grep -q "只有你看得到\|持股總覽" /tmp/rb.html && fail "專屬投資顧問頁不該有站長專屬內容"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/robot/holdings.json"); [ "$code" = 200 ] && grep -q weight_pct <(curl -s "$BASE/robot/holdings.json") && fail "訪客版不該有持股權重"
rpost() { curl -s -X POST -H "Content-Type: application/json" -d "$1" "$BASE/robot/api/advisor"; }
need "$(rpost '{"question":""}')" '請輸入問題' "空白問題應該擋下"
if [ -f site/robot/stocks.json ]; then
  need "$(rpost '{"question":"台積電和聯電哪個比較好？"}')" '"found":\["2330","2303"\]' "應該找得到台積電與聯電"
  python3 - <<'PY' || fail "訪客版資料不該包含只因站長持股才計算的股票"
import json
full = json.load(open("site/portfolio/advisor/stocks.json"))
guest = json.load(open("site/robot/stocks.json"))
assert "public_codes" not in guest
assert set(guest["price_codes"]) <= set(full.get("public_codes") or []), set(guest["price_codes"]) - set(full.get("public_codes") or [])
hidden = set(full["price_codes"]) - set(guest["price_codes"])
leak = [c for c in hidden if "risk" in guest["stocks"].get(c, {}) or "backtest" in guest["stocks"].get(c, {})]
assert not leak, leak
PY
fi
# 幫我找股票（選股機器人）：訪客版直接用；站長版在投資頁密碼後面
code=$(curl -s -o /tmp/fd.html -w '%{http_code}' "$BASE/robot/find/"); [ "$code" = 200 ] || fail "幫我找股票（訪客）應該 200，實際 $code"
grep -q "/robot/api/finder" /tmp/fd.html || fail "訪客版選股頁應該打 /robot/api/finder"
grep -q "免責聲明" /tmp/fd.html || fail "選股頁要有免責聲明"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/portfolio/advisor/find/"); [ "$code" = 401 ] || fail "站長版選股頁沒密碼應該 401，實際 $code"
r=$(curl -s -X POST -H "Content-Type: application/json" -d '{"question":"龍頭股"}' "$BASE/portfolio/api/finder"); need "$r" '請重新輸入密碼' "沒登入不能用站長版選股"
need "$(curl -s -X POST -H "Content-Type: application/json" -d '{"question":""}' "$BASE/robot/api/finder")" '請描述' "選股空白問題應該擋下"
echo "✅ 專屬投資顧問（訪客版）"

# 模擬交易（ACCESS_DEV_EMAIL=smoke@example.com）：報價用證交所即時盤面；依當下是否為交易時間走「立即成交」或「預約單」
me=$(curl -s "$BASE/api/sim/me"); need "$me" '"cash":1000000' "新帳戶應該有 100 萬"
need "$me" '"session":"' "帳戶要回傳交易時段"
q=$(curl -s "$BASE/api/sim/quote?code=0050"); need "$q" '"price"' "查不到 0050 報價"
need "$q" '"order_upper"' "報價要有可委託的漲停價"
need "$q" '"day":"20' "報價要帶即時盤面的資料日"
sr=$(curl -s "$BASE/api/sim/search?q=%E5%85%83%E5%A4%A7"); need "$sr" '"0050"' "用名稱「元大」應該搜得到 0050"
need "$(post /api/sim/order '{"code":"0050","side":"buy","shares":1500}')" '分開下單' "整股和零股混在一起應該擋下"
need "$(post /api/sim/order '{"code":"0050","side":"buy","shares":-1}')" '整數' "應該擋下負股數"
need "$(post /api/sim/order '{"code":"0050","side":"sell","shares":11}')" '持股不足' "沒有持股不能賣"
need "$(post /api/sim/order '{"code":"2330","side":"buy","shares":100000}')" '現金不足' "應該擋下超買"
need "$(post /api/sim/order '{"code":"0050","side":"buy","shares":1,"type":"limit","limit_price":0.01}')" '跌停' "限價超出漲跌停應該擋下"
up=$(echo "$q" | sed -n 's/.*"order_upper":\([0-9.]*\).*/\1/p'); lo=$(echo "$q" | sed -n 's/.*"order_lower":\([0-9.]*\).*/\1/p')
odd=$(python3 -c "print(round($lo+0.02,2))")
need "$(post /api/sim/order "{\"code\":\"0050\",\"side\":\"buy\",\"shares\":1,\"type\":\"limit\",\"limit_price\":$odd}")" '升降單位' "不符合升降單位應該擋下"
# 跌停價的限價買單：盤中通常掛著、非交易時間是預約單，兩種都應該進委託清單，而且可以取消
lo_order=$(post /api/sim/order "{\"code\":\"0050\",\"side\":\"buy\",\"shares\":1,\"type\":\"limit\",\"limit_price\":$lo}")
need "$lo_order" '"ok":true' "跌停價限價買單應該可以送出"
me=$(curl -s "$BASE/api/sim/me")
if echo "$lo_order" | grep -q '"filled":false'; then
  need "$me" '"status":"open"' "委託清單應該有掛單"
  oid=$(echo "$me" | sed -n 's/.*"orders":\[{"id":\([0-9]*\).*/\1/p')
  need "$(post /api/sim/cancel "{\"id\":$oid}")" '"ok":true' "取消委託失敗"
fi
r=$(post /api/sim/order '{"code":"0050","side":"buy","shares":10}')
if echo "$r" | grep -q '即時報價暫時讀不到'; then
  echo "⚠️ CI 主機這次連不到證交所即時報價，盤中成交測試略過（程式正確地拒絕用舊價格成交）"
elif echo "$me" | grep -q '"market_open":true'; then
  need "$r" '"filled":true' "盤中市價買單應該立即成交"
  need "$(post /api/sim/order '{"code":"0050","side":"sell","shares":4}')" '"ok":true' "盤中賣出失敗"
  need "$(curl -s "$BASE/api/sim/me")" '"shares":6' "持股應該剩 6 股"
else
  need "$r" '預約單' "非交易時間的市價單應該變成預約單"
  need "$r" '"filled":false' "預約單不會立即成交"
fi
need "$(post /api/sim/watch '{"code":"2330","on":true}')" '"ok":true' "加入自選失敗"
need "$(curl -s "$BASE/api/sim/watch")" '"2330"' "自選股清單沒有 2330"
ch=$(curl -s "$BASE/api/sim/chart?code=2330"); need "$ch" '"rows"' "應該有走勢資料"
echo "✅ 模擬交易"

# 市場頁：所有登入者都看得到，但不能出現持股提醒
code=$(curl -s -o /tmp/mk.html -w '%{http_code}' "$BASE/market/"); [ "$code" = 200 ] || fail "市場頁應該 200，實際 $code"
grep -q "持股提醒" /tmp/mk.html && fail "市場頁不該有持股提醒"
code=$(curl -s -o /tmp/wh.html -w '%{http_code}' "$BASE/whales/"); [ "$code" = 200 ] || fail "大佬持股頁應該 200，實際 $code"
grep -q "我的持股 × 大佬" /tmp/wh.html && fail "大佬持股頁不該有站長持股"
code=$(curl -s -o /tmp/us.html -w '%{http_code}' "$BASE/us/"); [ "$code" = 200 ] || fail "美股頁應該 200，實際 $code"
grep -q "持股提醒\|我的持股" /tmp/us.html && fail "美股頁不該有站長持股"
need "$(curl -s "$BASE/glossary.js")" '三大法人' "術語註解檔 glossary.js 應該要有內容"
echo "✅ 市場頁"

# 即時報價 API（來源暫時連不到也要回正常格式）
need "$(curl -s "$BASE/api/live?idx=1&tw=2330,abc")" '"updated"' "即時報價 API 格式不對"
echo "✅ 即時報價"

# 即時快報
n=$(curl -s "$BASE/api/news?cat=tw_stock"); need "$n" '"items":\[{' "即時快報沒有新聞"
need "$(curl -s "$BASE/api/news?cat=nope")" '沒有這個分類' "未知分類應該回錯誤"
# LINE webhook：沒有正確簽章一律拒絕
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H "Content-Type: application/json" -d '{"events":[]}' "$BASE/api/line/webhook"); [ "$code" = 401 ] || fail "LINE webhook 沒簽章應該 401，實際 $code"
need "$(curl -s "$BASE/pick/latest_line.json")" '"messages"' "應該有 LINE 用的今日一檔文字"
echo "✅ 即時快報"
