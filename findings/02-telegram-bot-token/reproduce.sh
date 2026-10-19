#!/bin/bash
# Reproduce: extract Telegram bot token from /user/trade-signals/1
# Requires: a session cookie jar after login (cookies_a.txt)
curl -sS -c cookies_a.txt -b cookies_a.txt \
  -H "User-Agent: Mozilla/5.0" \
  https://gainledgecapital.com/user/trade-signals/1 \
  | grep -oE 'telegram_bot_api[^"]*"[^"]+"'
