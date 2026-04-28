# gainledgecapital.com Livewire Security Audit — Running Notes

## Setup / Environment
- Authorized scope: gainledgecapital.com web app, Livewire attack surface.
- Tools: curl + bash (Python `requests` returned TLS upstream errors; HTTP/2 via curl works fine).
- Cookie jars: `cookies_a.txt` (Account A, id=136), `cookies_b.txt` (Account B, id=137).
- All requests use a Chrome 123 UA via `/tmp/req.sh`.
- Helpers: `lw_send.py` (Livewire 3 update sender), `scan.py`,
  `build_inventory.py`, probes in `probes/`.
- Polite rate-limit ≤ 2 req/sec.

## Fingerprint
- PHP/8.2.29 (X-Powered-By header).
- Livewire **v3.14.1** (extracted from `/livewire/livewire.js`).
  - Above 3.6.3 → CVE-2025-54068 RCE chain does NOT apply.
- Livewire update endpoint: `POST /livewire/update`.
- CSRF: per-page `<meta name="csrf-token">` plus per-form `_token`.

## Path probe results (low-priv Account A)
| Path | Status |
|---|---|
| /admin | 404 |
| /admin/login | 200 — Livewire `admin.auth.login` |
| /admin/dashboard | 302 → /user/dashboard (exists) |
| /admin/users | 302 → /user/dashboard |
| /admin/users/1 | 302 → /user/dashboard |
| /admin/users/137 | 302 → /user/dashboard |
| /admin/users/100 | 404 |
| /admin/users/200 | 404 |
| /admin/settings | 302 → /user/dashboard |
| /admin/plans | 302 → /user/dashboard |
| /admin/account-settings | 302 → /user/dashboard |
| /admin/settings/general | 302 → /user/dashboard |
| /filament /nova /horizon /telescope /_ignition | 404 |
| /login /register /forgot-password | 200 |
| /admin/forgot-password | (link only) |
| /.env  /.git/config | 406 / 403 (blocked) |

## Credentials confirmed
- Account A: `joskemeulemans@hotmail.com` / `JOSPAS123` (the trailing `>`
  in the prompt was a typo)
- Account B: `markmeulemans@hotmail.com` / `MarkPass123!`
- Both redirect to `/user/dashboard` after login.

## User route map (from authenticated dashboard + crawl)
```
/user/dashboard
/user/account-settings
/user/contact-support
/user/copy-trader  /user/copy-trader/copiedtrade
/user/crypto-swap/{assets,transactions,coin/<sym>,convert/<sym>}
/user/deposit
/user/investment/{buy-plan,my-plans}
/user/kyc/{start,submit}
/user/notifications
/user/referral
/user/trade-signals/{id}
/user/transactions/{deposit,withdrawal,others}
/user/transfer-fund
/user/withdraw/request
/language/<locale>
/ref/<username>  (302)
```

## Component inventory (21 unique)
See `inventory.json`. Highlights:
- `user.account-settings.show` — has User model in `data.user`, form props
  for name/email/phone/country/address/username and bank/crypto wallet
  fields; methods `saveProfile`, `saveWithdrawalMethod`, `changePassword`.
- `user.kyc.form` — `status` is a public property w/ default
  "under review", **mass-assignable** (Finding 06).
- `user.trade-signal` — leaks `telegram_bot_api`, `chat_id`, internal
  `website` URL in its data (**Finding 02**).
- `user.fund-transfer` — sender's password is required for transfers
  (correct design).
- `profile.delete-user-form`, `profile.logout-other-browser-sessions-form`,
  `profile.two-factor-authentication-form` — Jetstream-style modals
  gated by Fortify password-confirmation (correct).

## Hard-rule reminders
- No destructive actions (delete, force-delete, transfer, withdrawal,
  payment) without explicit confirmation in this file or a non-destructive
  substitute. **None executed.**
- KYC `submit()` was NOT run end-to-end: would persist a permanent KYC
  row on my account. Documented as F06 "potential, requires code review".
- Telegram bot token: did NOT use it to make any Telegram API call;
  leak alone is the finding.
- No writes to other users' data.

## Probes & decisions

### Mass-assignment
- `user.<x>` dotted-model assignment → blocked at Livewire 3 framework
  layer with `Can't set model properties directly` (returns 500 with full
  stack trace → Finding 01).
- Top-level undeclared prop assignment → `PublicPropertyNotFoundException`
  (also 500 + stack trace).
- KYC `status` is one of the rare public scalar properties not in the
  validation rules → Finding 06.

### saveProfile readonly bypass test
- Sent `email = markmeulemans@hotmail.com` + `saveProfile`. Snapshot
  reflected the change with no validation error.
- Reload showed original email persisted → server-side whitelist in
  `saveProfile()` is what's keeping it safe; readonly HTML alone is not.
- Logged as Finding 05 (info, structural smell).
- changePassword correctly requires current_password.

### Method enumeration
- Tested non-destructive method names (`loadUser`, `selectUser`, `setUserId`,
  `setUser`, `viewAs`, `impersonate`, `loginAs`, `switchUser`, `export`,
  `mountAction`, `mountTableAction`, ...). All returned
  `MethodNotFoundException` on `user.account-settings.show`. Probe was
  cut short when Account A's session expired and was re-established.
- `mount` correctly blocked with `DirectlyCallingLifecycleHooksNotAllowedException`.

### IDOR / cross-tenant
- Diffed snapshots between Account A and B for the same paths — no
  component-level differences; only per-user data differences.
- `/user/trade-signals/<arbitrary id>` returns the same leaked
  `set` row (Finding 02) — but no per-user data leaks across IDs.
- `/admin/users/<id>` distinguishes exist (302) from absent (404)
  → Finding 04.
- Snapshot replay anonymously: `user.account-settings.show` snapshot from
  Account A replayed via `/livewire/update` from an anonymous jar →
  302 to `/login`. Properly gated.

### SQLi
- `'`, `' OR 1=1--`, `; DROP--` on search/sort/method-id fields → no SQL
  errors leaked. `UNION SELECT 1--` blocked by WAF (HTTP 406).
- Integer route segments (e.g. selectedMethod=-1, =999999) → 404.
  Suggests `findOrFail` style binding.

### Info-disclosure path scan
- `.env` 406 (WAF block). `/.git/{config,index,HEAD,COMMIT_EDITMSG,
  refs/heads/master}` 403. Composer/Yarn lock files 503/404. No leaks.
- `robots.txt` is `User-agent: *\nDisallow:` (24 bytes; no info).
- `/storage/settings/<hash>.png` is 200 (the public site logo —
  expected).

## Findings register
| # | Severity | Title | Folder |
|---|---|---|---|
| 02 | High | Telegram bot API token in `user.trade-signal` snapshot | `findings/02-telegram-bot-token/` |
| 01 | Medium | `APP_DEBUG=true` on production | `findings/01-debug-mode/` |
| 03 | Medium | `window.Laravel.user` full-row exposure | `findings/03-user-object-leak/` |
| 06 | Medium (potential) | KYC `status` is mass-assignable | `findings/06-kyc-status-mass-assignable/` |
| 04 | Low | User enumeration via `/admin/users/{id}` | `findings/04-user-enumeration/` |
| 05 | Info | Readonly inputs not server-enforced | `findings/05-readonly-bypass-design/` |

## Things tested but NOT vulnerable / not exploitable
- Privilege escalation to admin via mass-assignment (blocked at Livewire
  framework + server-side `saveProfile` whitelist).
- Cross-tenant data access via component snapshots.
- SQL injection on `search`, `sort_value`, `selectedMethod`.
- Anonymous Livewire component access (`/livewire/update` is
  middleware-gated).
- Email change without `current_password` (UI shows readonly; server-side
  drops the field).
- changePassword without `current_password`.
- `/admin` paths via low-priv session (proper guard).
- `.env`, `/.git/*` direct read (WAF / Apache config).
- Anonymous snapshot replay (auth middleware blocks).
- CVE-2025-54068 RCE — version 3.14.1 not vulnerable.

## Final deliverables
- `report.md` — this engagement's report.
- `notes.md` — this file.
- `inventory.json` — component catalog.
- `findings/01..06-*/` — per-finding evidence packs.
- `pages/`, `snapshots/` — captured HTML and Livewire snapshots.
- `scan.py`, `lw_send.py`, `build_inventory.py`, `probes/*.py` — tools used.
- `request_log.jsonl` — recorded Livewire requests (partial, only
  probe-driven traffic).
