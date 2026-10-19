# Finding 09 — Crypto-swap `convert()` lets the client mint arbitrary balance (CRITICAL)

## Summary
The Livewire component `user.crypto-swapping.conversion`
(at `/user/crypto-swap/convert/{symbol}`) accepts a client-supplied
`quantity` property and uses it as the amount credited to the destination
asset, **without** computing it from `from_amount × rate`. By sending
`quantity = N` for any N along with the `convert()` call, the server
credits the user's destination crypto balance with N units regardless of
the user's actual `account_bal`.

In other words: **`convert()` mints crypto out of thin air**.

## Severity
**Critical** — CVSS-ish 9.1
(AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N).

A registered low-priv user can fabricate any amount of any supported asset
on the platform. If the platform later allows withdrawal of this asset, an
attacker drains real funds from the company's hot wallet. Even if
withdrawal is gated, every internal accounting metric is broken (estimated
balance, ROI, plan eligibility, etc.).

## Evidence
While probing `convert()`'s input validation as part of the engagement, I
sent the request below ONCE, expecting either an "insufficient funds"
error (Account A's `account_bal` is `0.00`) or a strict-validation
rejection.

Request:
```
POST /livewire/update
{
  "_token":"<csrf>",
  "components":[{
    "snapshot":"<wire:snapshot of user.crypto-swapping.conversion>",
    "updates":{"from_amount":"100","to_amount":"100","quantity":"100","to_deduct":"0"},
    "calls":[{"path":"","method":"convert","params":[]}]
  }]
}
```

Response: HTTP 302 → `/user/crypto-swap/assets` (the success path).

Refetching `/user/crypto-swap/assets` shows:
- `account_bal: 0.00` (unchanged — no deduction happened)
- BTC `balance: "100.00000000"` (100 BTC newly credited)
- `estimated_balance: 8786700` (≈ 100 BTC × $87,867 = **$8,786,700** of
  fabricated USD-denominated balance in the user's account)

Refetching `/user/crypto-swap/transactions` shows the swap row recorded:
```
From Account Balance  →  Bitcoin(BTC)
Amount: $100.00       Received: 100 Bitcoin(BTC)        Apr 28, 2026 08:29 PM
```

Earlier probes with `quantity` *not* in the `updates` showed
`Received: 0 Bitcoin(BTC)` regardless of `from_amount` (e.g. `from_amount`
of $1, $1,000,000, $1 — all received 0). That isolates `quantity` as the
client-controlled credit amount.

(Captured: `swap_history.html`, `state_after_bug.txt`.)

## What I did NOT do (engagement guardrail)
I did not:
- Withdraw the fabricated 100 BTC.
- Convert the fabricated BTC to USDT or any other "stable" asset.
- Send the BTC to any external wallet.
- Use the BTC to buy an investment plan.

The fabricated balance is sitting on Account A. The site owner should
manually zero out User #136's BTC balance after reading this report (and
audit the swap history for the fake row).

## Root cause (best-effort code-review hypothesis)
The component appears to do something like:
```php
public function convert() {
    $this->validate([
        'from_amount' => 'required|numeric|gt:0',
    ]);
    $this->user->cryptoAccount($this->from_currency)->decrement('balance', $this->to_deduct);
    $this->user->cryptoAccount($this->to_currency)->increment('balance', $this->quantity);
    SwapTransaction::create([...]);
    return redirect()->route('user.crypto-swap.assets');
}
```
Both `to_deduct` and `quantity` are public Livewire properties, both
client-supplied. Validation only checks `from_amount > 0`. Neither
`to_deduct` nor `quantity` is bounded; neither is recomputed server-side
from `from_amount × rate`.

## Recommendation
1. **Immediately disable the `/user/crypto-swap/*` flow** (feature flag,
   middleware abort, or remove the route) until the convert math is fixed.
2. Compute `to_deduct` and `quantity` *server-side* in the action method
   from `from_amount` and the live `from_currency.price_in_usd`,
   `to_currency.price_in_usd`. Never trust either value from the client.
3. Mark `to_deduct` and `quantity` as `#[Locked]` properties (or remove
   them as public properties entirely) so they cannot be overridden via
   the wire protocol.
4. Add the standard set of guardrails:
   - `abort_unless($this->user->is(auth()->user()), 403)` (Finding 07).
   - DB transaction wrapping decrement+increment.
   - Reject if from-balance is insufficient *before* increment.
5. Audit `joinPlan`, `transfer`, `requestWithdrawal`, and any other
   amount-handling action for the same client-controlled-amount pattern.
6. Audit historical `crypto_swap_transactions` rows for any user who
   abused this in the past.
