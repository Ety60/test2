# Security Audit Report — gainledgecapital.com

**Engagement:** Authorized black-box web-app pentest of GainLedge Capital,
focused on the Laravel Livewire attack surface.
**Date of testing:** 2026-04-28.
**Tester accounts:**
- Account A — `joskemeulemans@hotmail.com` (low-priv "User", id=136)
- Account B — `markmeulemans@hotmail.com` (low-priv "User", id=137)
**Target version:** PHP 8.2.29, Laravel + Livewire **3.14.1**.
**Scope:** `gainledgecapital.com` web app. Out of scope: third-party
integrations (Pusher, Telegram, hosting), DoS, social engineering.

## Executive summary

Six issues are reported below.

| # | Severity | Title |
|---|---|---|
| 02 | **High** | Telegram bot API token leaked in `user.trade-signal` Livewire snapshot |
| 01 | Medium | `APP_DEBUG=true` on production — full stack traces & paths leak |
| 03 | Medium | `window.Laravel.user` exposes the entire `users` row including `is_admin`, `withdrawal_otp`, role/permission lists |
| 06 | Medium *(potential)* | `status` is a public Livewire property on `user.kyc.form` — mass-assignable; would let a user self-approve KYC if `submit()` persists `$this->all()` (unconfirmed because end-to-end PoC requires a destructive write to my own account) |
| 04 | Low | User-ID enumeration via `/admin/users/{id}` (auth runs after route-model binding) |
| 05 | Info | `readonly` HTML inputs are the only protection on identity fields (`email`, `username`, `country`, `address`); not currently exploitable but a structural smell |

The most pressing remediation is **rotating the Telegram bot token** (Finding 02)
and **disabling `APP_DEBUG`** in production (Finding 01). The KYC `status`
finding (06) is the next priority for an internal code review since it could
plausibly be a real KYC bypass.

I attempted but **did not** find:
- Privilege escalation to the admin panel via mass assignment, hidden API,
  IDOR, or method enumeration. The admin panel sits on a separate
  Spatie-Permission-style guard; low-priv users cannot reach it.
- Cross-tenant data access. Snapshots between Account A and B show only
  per-user data; no admin-tier or peer data leaked through any user component.
- SQL injection in `search`, `sort_value`, `selectedMethod`, `paginators`
  fields. The application appears to use parameterised Eloquent queries; a
  WAF additionally blocks obvious `UNION SELECT` payloads.
- Account-takeover via `saveProfile` (HTML readonly bypass): the server
  whitelists which fields it persists, so writing `email` or `username` from
  the wire protocol does not actually update the DB.
- Anonymous Livewire component instantiation: `/livewire/update` is gated by
  the same auth middleware as the originating page.
- `.env`, `/.git/*`, `composer.json`, etc. — all blocked at the web tier
  (403 / 406 / 503).
- CVE-2025-54068 (Livewire ≤ 3.6.3 RCE candidate) does **not** apply — the
  installed version is 3.14.1.

## Findings

### Finding 02 — Telegram bot API token leaked (High)
**Where:** Livewire component `user.trade-signal` rendered at
`/user/trade-signals/{id}` (any id).
**What:** The `set` row inside the component data ships the bot's
long-lived API token in plaintext to every authenticated browser:

```
"telegram_bot_api": "7126975865:AAFu8EqrY6uqO9HxY6lL6xNhTM_ZBp-oNRo"
"chat_id":          "-1002243300399"
"website":          "https://lab.luxehavenhotel.com/get-started"
```

**Repro:**
```
curl -sS -c jar -b jar https://gainledgecapital.com/user/trade-signals/1 \
  | grep -oE 'telegram_bot_api[^"]*"[^"]+"'
```
**Impact:** Possession of the bot token grants read+publish on the
trade-signals Telegram channel — an attacker can publish fake "buy now"
signals to subscribers, and read any DM the bot is part of.
**Fix:** Rotate the token (`/revoke` in BotFather), then refactor the
component so secret fields are never assigned to public Livewire properties
or serialised into the snapshot. Use `#[Locked]` / private members /
projection to a view-model.

Evidence: `findings/02-telegram-bot-token/`.

### Finding 01 — Debug mode in production (Medium)
**Where:** All routes (any route that throws).
**What:** Whoops/Ignition-style debug HTML is returned with full stack
trace and absolute paths (`/home/gainledg/public_html/...`).
**Repro:** any `POST /livewire/update` whose `updates` field tries to set
a model property via dotted syntax (`{"user.role":"X"}`) — the framework
throws `Can't set model properties directly` and the server returns a 500
HTML page disclosing the trace.
**Impact:** path / framework-version / line-number disclosure that helps
chain other vulnerabilities (LFI, deserialization, debug-mode-only Livewire
CVEs e.g. CVE-2024-13918, CVE-2024-13919).
**Fix:** `APP_DEBUG=false` and `php artisan config:cache`.

Evidence: `findings/01-debug-mode/response_user_role_500.html`.

### Finding 03 — `window.Laravel.user` full row exposure (Medium)
**Where:** Every authenticated page injects:
```
window.Laravel = { user: { ... 58 columns ... }, pusherKey, pusherCluster };
```
**What:** Among the leaked columns: `is_admin`, `admin_type`,
`admin_two_factor_code`, `pass_two_factor`, `enable_2fa`, `token_2fa_expiry`,
`withdrawal_otp`, `withdrawal_otp_expired_at`, `roles`, `permissions`,
`assigned_to`, `customer_status`.
**Impact:** The `withdrawal_otp` exposure is the worst case — if the column
is populated during a withdrawal flow, an attacker reading the page
(via XSS, browser extension, screenshare) instantly has the live OTP.
**Fix:** Project the user object to a strict whitelist before rendering.

Evidence: `findings/03-user-object-leak/window_laravel_user.json`.

### Finding 06 — KYC `status` is mass-assignable on the Livewire component (Medium, potential)
**Where:** `user.kyc.form` at `/user/kyc/submit`, method `submit()`.
**What:** `public string $status` is part of the snapshot data, and the
wire protocol accepts `updates: {"status": "approved"}` without error.
The validation rules in `submit()` cover 11 input fields but **not**
`status`, suggesting the `submit()` body persists `$this->all()` (or a
list that includes `status`).
**Confidence:** I did not run end-to-end persistence (would require
filling 11 mandatory fields and uploading 2 images on my own account —
within the engagement's no-destructive-writes guardrail). Treat as a
high-priority code-review item.
**Fix:** Mark `$status` as `#[Locked]` and persist `'status' => 'under review'`
explicitly in `submit()`.

Evidence: `findings/06-kyc-status-mass-assignable/`.

### Finding 04 — User enumeration via `/admin/users/{id}` (Low)
**Where:** Anonymous & authenticated GET to `/admin/users/{id}`.
**What:** Existing IDs return 302 (to `/admin/login` for anon, to
`/user/dashboard` for low-priv); non-existing IDs return 404. The
existence check happens before the auth guard.
**Fix:** Resolve route-model bindings inside the auth-protected route
group, or return 404 to unauthorised callers regardless of existence.

Evidence: `findings/04-user-enumeration/`.

### Finding 05 — Readonly HTML inputs are the only protection on identity fields (Info)
**Where:** `user.account-settings.show`, fields `email`, `username`,
`country`, `address`.
**What:** These fields are `readonly` in HTML but the Livewire
`wire:model` properties accept arbitrary updates from the wire protocol.
Currently mitigated by a server-side whitelist in `saveProfile()` (the
DB write does not include them). Future contributors adding a similar
field may not realise this and skip server-side validation, leading to
account-takeover via email rewrite.
**Fix:** Use Livewire's `#[Locked]` attribute, or split read-only
display fields off from writable properties.

Evidence: `findings/05-readonly-bypass-design/`.

## Methodology

### Phase 0 — Fingerprint
Confirmed Livewire 3.14.1 (above the 3.6.3 RCE bound), PHP 8.2.29.
Mapped admin paths: `/admin/login` (200), `/admin/dashboard`,
`/admin/users{,/{id}}`, `/admin/settings{,/general}`, `/admin/plans`,
`/admin/account-settings` — all 302 to `/user/dashboard` from a low-priv
session, and 302 to `/admin/login` from an anon session.

### Phase 1 — Component inventory
Crawled 22 authenticated user pages. Extracted 21 unique Livewire
components (see `inventory.json`). Highlights with sensitive-name keywords:
`admin.auth.login` (admin login page),
`profile.delete-user-form`, `profile.logout-other-browser-sessions-form`,
`profile.two-factor-authentication-form` (Jetstream-style modals correctly
gated by Fortify password-confirmation).

### Phase 2 — Attack-surface expansion
Diffed Account A vs Account B snapshots — no role-gated component appeared
on either side. JS bundle mining produced no admin URL pattern beyond the
already-discovered `/admin/*`.

### Phase 3 — Probes
- **3.1 Mass-assignment via `<modelprop>.<column>`** — blocked at the
  Livewire framework level
  (`Livewire\Features\SupportModels\ModelSynth::set` throws
  "Can't set model properties directly"). This was the trigger for
  Finding 01.
- **3.1 Top-level prop assignment** — properties not declared on the
  component (e.g. `role`, `is_admin`) raise
  `PublicPropertyNotFoundException`; the existing public properties
  on `user.account-settings.show` are bound to the user-editable form
  and do **not** include privilege fields.
- **3.2 Method enumeration** — no privileged methods discovered. The
  destructive verbs (`delete`, `destroy`, `forceDelete`, ...) were not
  invoked in line with the engagement guardrails.
- **3.3 IDOR** — `/user/trade-signals/{id}` accepts arbitrary numeric
  IDs and returns the same `set` row (the leaked Telegram token, hence
  Finding 02). `/admin/users/{id}` enumeration → Finding 04.
  Snapshot replay across sessions is blocked by middleware (validated
  by replaying Account A's `user.account-settings.show` snapshot from an
  anonymous session — server returns 302 to `/login`).
- **3.4 SQLi probes** — `'`, `' OR 1=1--`, `; DROP--`, `UNION SELECT 1--`
  on `search`, `sort_value`, `selectedMethod`. No SQL errors leaked;
  `UNION SELECT 1--` was rejected by a WAF with HTTP 406; integer
  fields silently 404 on out-of-range values.
- **3.5 Validation reflection** — only the standard Laravel validation
  message strings appeared; no XSS / SQL strings reflected.

## Scope boundaries respected
- No destructive writes to other users' data.
- No DoS, no payment flows triggered, no withdrawal flows triggered.
- KYC `submit()` was not run end-to-end (would create a permanent KYC
  record on my account); the finding is reported as "potential — code
  review needed".
- Did not exercise the leaked Telegram bot token to make any Telegram
  API call; finding rests on the in-snapshot disclosure alone.
- `.env`, `/.git/*` were probed via single GETs only (no recursive
  download attempts).

## Deliverables in this directory
- `report.md` (this file)
- `notes.md` — running log of every probe and decision
- `inventory.json` — Livewire component catalog
- `request_log.jsonl` — every Livewire `/livewire/update` request made
  (via `lw_send.py`'s logger; partial — populated only for the
  programmatic probes)
- `findings/0*/` — per-finding evidence packs (analysis.md + raw responses)
- `pages/`, `snapshots/` — raw HTML and snapshot dumps used as evidence
