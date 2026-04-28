# Finding 03 — Full user row exposed in `window.Laravel` on every authenticated page

## Summary
Every authenticated page injects a JavaScript global of shape

```js
window.Laravel = {
  user: { ... full users-table row ... },
  pusherKey: "e10972754f11b36a3ddd",
  pusherCluster: "mt1"
}
```

The `user` object includes all 58 columns of the `users` table for the
currently-authenticated user. The same payload is rendered server-side and is
visible in the page HTML (no script needs to run to read it).

## Severity
**Medium** (CVSS-ish 4.3, AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N).

Internally a low-priv user can already see most of these fields via legitimate
profile pages, but the dump also includes fields that should never reach the
client and that are time-sensitive sensitive:

- `is_admin`, `admin_type`, `admin_two_factor_code`, `pass_two_factor`
- `enable_2fa`, `token_2fa_expiry`, `two_factor_confirmed_at`
- **`withdrawal_otp`** and **`withdrawal_otp_expired_at`**
- `received_signup_bonus`, `account_bal`, `roi`, `bonus`, `ref_bonus`
- `can_withdraw`, `can_deposit`, `can_trade`, `trade_mode`
- `customer_status`, `assigned_to` (CRM-style assignment)
- `permissions`, `roles` (Spatie Permission package — sometimes eager-loaded)
- `is_online`, `last_seen` (privacy)

The most consequential field is **`withdrawal_otp`**: if the application ever
stores a one-time withdrawal code in this column (for SMS / email-OTP-style
2FA on withdrawals), it is shipped to the browser on every page load — an
XSS or cross-tab JavaScript reader can immediately exfiltrate the live OTP,
defeating the OTP control. The OTP was `null` for the test account because
no withdrawal was in flight, but this is a class-level issue: either the
column is unused (then drop it) or it is used (then never expose it).

## Affected
- Every authenticated page (verified on 17 distinct user routes).
- The dump is rendered into the HTML, so even no-script clients see it.
- Snapshot saved at `window_laravel_user.json`.

## Reproduction
```
curl -sS -c jar -b jar https://gainledgecapital.com/user/dashboard \
  | grep -oE 'window\.Laravel\s*=\s*\{[^<]+\};'
```

## Impact
- An XSS in any vendor / template / Livewire component immediately yields
  `is_admin`, role/permission list, `withdrawal_otp`, `assigned_to`.
- An attacker with brief access to the rendered HTML (eg an in-browser
  malicious extension, screen-share, cached page on a shared computer)
  can read the full user row — which includes the live withdrawal OTP if
  one is in flight.

## Recommendation
1. Project the user object to a strict whitelist before serialising — eg
   `{id, name, username, email, profile_photo_path}` is plenty for a
   front-end greeting / Pusher private-channel auth.
2. Never expose `is_admin`, `admin_*`, `*_otp*`, `assigned_to`, `permissions`,
   `roles`, `customer_status`, `email_preference`, `pass_two_factor`,
   `enable_2fa`, `token_2fa_expiry` to the browser.
3. Audit any code that writes `withdrawal_otp` — store the OTP hashed (like
   passwords) and verify by comparison, never persist the cleartext.
