#!/bin/bash
# 在 GitHub Actions 裡查 D1（模擬交易、顧問追蹤清單、LINE 群組都存在這裡）。
# 用法：scripts/d1.sh "SELECT ..."  → 印出 results 陣列（JSON）。需要 CLOUDFLARE_API_TOKEN、CLOUDFLARE_ACCOUNT_ID。
# 自己產生一份臨時 wrangler 設定，不依賴建站流程後面才產生的 wrangler.toml。
set -euo pipefail
id=$(wrangler d1 list --json | jq -r '.[] | select(.name=="craig-finance-sim") | .uuid')
[ -n "$id" ] || { echo "找不到 D1 資料庫" >&2; exit 1; }
cfg="$(mktemp -d)/wrangler.toml"
printf 'name = "d1-query"\ncompatibility_date = "2024-09-23"\n\n[[d1_databases]]\nbinding = "DB"\ndatabase_name = "craig-finance-sim"\ndatabase_id = "%s"\n' "$id" > "$cfg"
wrangler d1 execute craig-finance-sim --remote --json --config "$cfg" --command "$1" | jq -c '.[0].results'
