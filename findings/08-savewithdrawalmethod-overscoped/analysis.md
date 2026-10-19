# Finding 08 — `saveWithdrawalMethod` persists fields not present in its visible form

## Summary
The `saveWithdrawalMethod()` action on `user.account-settings.show`
silently persists **eight** financial-account columns even though the
visible withdrawal-tab form only contains three input fields
(`btc_address`, `eth_address`, `usdt_address`).

Verified persistence (each tested by sending the field via Livewire
`updates`, calling `saveWithdrawalMethod`, and re-fetching to confirm
the DB write):

| Field | In visible form? | Persisted? |
|---|---|---|
| `btc_address` | Yes | Yes |
| `eth_address` | Yes | Yes |
| `usdt_address` | Yes | Yes |
| `ltc_address` | **No** | **Yes** |
| `account_name` | **No** | **Yes** |
| `account_number` | **No** | **Yes** |
| `bank_name` | **No** | **Yes** |
| `swift_code` | **No** | **Yes** |
| `email` (control) | n/a | No (whitelisted out — good) |
| `phone_number` (control) | n/a | No (whitelisted out — good) |

So the whitelist is broader than the form, but it does not extend to
identity columns (name/email/username/phone) — saveProfile handles those.

## Severity
**Low standalone, High when chained with Finding 07** —
CVSS-ish 4.3 standalone, 7.1 chained.

Standalone:
- A user can set bank-account fields (`account_name`, `account_number`,
  `bank_name`, `swift_code`) without the visible UI ever exposing them.
  If any other code path (admin verification, KYC, support ticket, withdrawal
  approval workflow) relies on bank fields being changeable only via a
  separate gated form, that gate is bypassable from the wire protocol.
- The user has no visibility into what they wrote, since the form doesn't
  surface those values back. Writes are blind from a UX standpoint.

Chained with **Finding 07**:
- Replaying another user's signed snapshot to `/livewire/update` and calling
  `saveWithdrawalMethod` with `btc_address: <attacker_wallet>` rewrites that
  user's withdrawal address.
- The next time the victim withdraws to Bitcoin, the funds go to the
  attacker.

## Affected
- Component: `user.account-settings.show`
- Method: `saveWithdrawalMethod()`
- Form: `/user/account-settings` → "Withdrawal" tab.

## Reproduction
```
# 1. Login as Account A. Get a fresh wire:snapshot of user.account-settings.show.
# 2. POST /livewire/update with:
{
  "_token": "<csrf>",
  "components": [{
    "snapshot": "<wire:snapshot>",
    "updates": {
      "account_number": "PROBE_ACCT",
      "bank_name":      "PROBE_BANK",
      "swift_code":     "PROBE_SWIFT",
      "ltc_address":    "PROBE_LTC"
    },
    "calls": [{"path":"","method":"saveWithdrawalMethod","params":[]}]
  }]
}
# 3. Re-fetch /user/account-settings — all four fields are persisted in the
#    new snapshot (and in the DB row).
```

I tested-and-reverted: each field was set to `PROBE_*`, immediate
re-fetch confirmed the persistence, then the same call with `null` values
restored the original `null` state. Final state of Account A:
```
account_name: None
account_number: None
bank_name: None
swift_code: None
btc_address: None
eth_address: None
ltc_address: None
usdt_address: None
```

(See `probe_evidence.txt` for the captured request/response timestamps.)

## Recommendation
1. In `saveWithdrawalMethod()`, persist only the visible-form fields:
   ```php
   $this->user->update($this->only([
     'btc_address', 'eth_address', 'usdt_address'
   ]));
   ```
   If LTC and bank-account fields are intended to be editable, expose them
   in the form **and** validate them server-side (BTC/ETH address format,
   IBAN/SWIFT format, KYC gating).
2. Pair with Finding 07: add `abort_unless($this->user->is(auth()->user()), 403)`
   at the top of every action method.
3. Audit `saveProfile()`, `joinPlan()`, `submit()` (KYC), `transfer()`
   (fund-transfer), `requestWithdrawal()` for the same pattern of
   "method whitelist wider than form".
