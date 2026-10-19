# Finding 07 — Cross-tenant data exposure via Livewire snapshot replay

## Summary
Livewire component snapshots (`wire:snapshot`) are signed with an HMAC of `APP_KEY`,
which protects against tampering but **does not bind the snapshot to the
authenticated user's session**. Components such as `user.account-settings.show`
and `user.notifications` re-hydrate `$this->user` from the snapshot's `key`
field rather than from `auth()->id()`, and never re-check that the rehydrated
user matches the current session.

As a result, any party who comes into possession of another user's signed
snapshot can submit it to `/livewire/update` from their own authenticated
session and:

1. **Read** the target user's PII back through the response
   (name, email, username, phone_number, country, address, plus any
   wallet/bank fields the target has saved).
2. **Write** to the target user via any save action that updates
   `$this->user` (validated separately in Finding 08).

## Severity
**High (conditional on snapshot exfiltration vector)** — CVSS-ish 7.1
(AV:N/AC:H/PR:L/UI:N/S:U/C:H/I:H/A:N).

The HMAC means an attacker can't *forge* a snapshot for an arbitrary user_id
without `APP_KEY`, so this is currently not a one-click exploit. However:
- Any feature that ever returns another user's snapshot (admin-side user
  view, support-ticket render, copy-trader profile preview, referral viewer,
  cached/CDN page, Sentry/Bugsnag breadcrumb that captures Livewire payloads,
  shared screen, browser extension, etc.) becomes a one-shot pivot to full
  PII read and to mass-assignment writes.
- `APP_DEBUG=true` (Finding 01) plus any chain to APP_KEY disclosure makes
  forging trivial.
- The class of bug is a "trust the data, not the session" anti-pattern; it
  will be re-introduced by every contributor adding a similar component if
  the framework defaults are not corrected.

## Affected
- `user.account-settings.show` (`/user/account-settings`) — re-hydrates
  `$this->user` from snapshot key.
- `user.notifications` (`/user/notifications`) — same.
- Likely every other component that binds a User model into `data.user`.

## Reproduction (read-only PoC, demonstrated)
```
# 1. Log in as Account A (id=136). Cookie jar = cookies_a.txt.
# 2. Log in as Account B (id=137). Cookie jar = cookies_b.txt.
# 3. As Account B, fetch a fresh /user/account-settings page and extract the
#    wire:snapshot for `user.account-settings.show`. Save raw HTML-decoded
#    snapshot string. (See B_signed_snapshot.json.)
# 4. As Account A: get a CSRF token from any authed page, then POST it as:

curl -sS -c cookies_a.txt -b cookies_a.txt \
  -X POST https://gainledgecapital.com/livewire/update \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://gainledgecapital.com' \
  -H 'Referer: https://gainledgecapital.com/user/account-settings' \
  --data-binary '{
    "_token": "<csrf from A>",
    "components": [{
      "snapshot": "<B-signed snapshot, raw>",
      "updates": {},
      "calls": []
    }]
  }'
```
Response is HTTP 200 with B's full data:
```
"name":"Mark Meulemans","email":"markmeulemans@hotmail.com",
"phone_number":"0687943512","username":"markske","country":"France",
"user":[null,{"class":"App\\Models\\User","key":137,"s":"mdl"}], ...
```

Account A is the authenticated session, but the response renders
Account B's PII — the component trusts `key:137` from the snapshot.

## Write-side impact (not executed, by engagement guardrail)
Combined with **Finding 08**, calling `saveWithdrawalMethod` with B's
snapshot would persist any `updates` (wallet/bank fields) onto User B's
row, since `$this->user->update($only)` operates on the rehydrated User #137.
We did not execute this on Account B per the no-writes-to-other-users rule;
the chain is documented for the code-review.

## Recommendation
1. Inside every Livewire component that has an authenticated user model,
   add an explicit check at the top of every action method:
   ```php
   abort_unless($this->user->is(auth()->user()), 403);
   ```
   Or, even better, **never serialize another user's model into a
   long-lived public property** — re-resolve `auth()->user()` in each
   action.
2. Use Livewire 3's `#[Locked]` attribute on properties that hold a User
   model, paired with the explicit auth check.
3. Consider rotating `APP_KEY` on detection of any leak path that exposes
   signed snapshots (the rotation invalidates all live snapshots).

## Evidence
- `B_signed_snapshot.json` — Account B's signed snapshot.
- `replay_response.json` — server response when replayed from Account A.
