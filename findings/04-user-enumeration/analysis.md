# Finding 04 — User enumeration via `/admin/users/{id}` (auth-after-resolve)

## Summary
The route `/admin/users/{id}` performs route-model-binding (or equivalent
existence check) **before** the admin auth middleware runs. As a result,
anyone — including unauthenticated visitors — can distinguish "user
exists" (HTTP 302 → /admin/login) from "user doesn't exist" (HTTP 404).

## Severity
**Low / Informational** (CVSS-ish 3.7, AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N).

Lets an attacker enumerate the entire users table size, find live IDs to
target with phishing or password-reset, and derive sign-up rate.

## Affected
- `GET /admin/users/{id}`
- Confirmed for IDs `{1, 137}` (302→/admin/login, exist) vs
  `{100, 200, 5000}` (404, do not exist).

## Reproduction
```
$ curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
    https://gainledgecapital.com/admin/users/1
302 https://gainledgecapital.com/admin/login

$ curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' \
    https://gainledgecapital.com/admin/users/200
404
```

The same is observable from a logged-in low-priv user:
`/admin/users/{exists}` → 302 to `/user/dashboard`,
`/admin/users/{absent}` → 404.

## Impact
- Enumerate active accounts (effectively `MAX(id)` and gaps in [1..N]).
- Identify high-value (low) IDs — typically founders / admins are early IDs.
- Fuels targeted password-reset / phishing once combined with the email
  guess (`first_initial + last_name@common-domain.tld`).

## Recommendation
- Run the auth middleware before route-model-binding for the entire
  `/admin/*` group. In Laravel, declare:
  ```php
  Route::middleware(['auth:admin'])->prefix('admin')->group(function () {
      Route::get('users/{user}', ...);
  });
  ```
  and ensure the binding happens inside the middleware-protected group.
- Alternatively, in the controller, return 404 when the actor is not
  authorised — never differentiate exist vs doesn't-exist for an anonymous
  visitor.
