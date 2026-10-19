# Finding 02 — Telegram bot API token shipped to every authenticated client

## Summary
The component `user.trade-signal` (rendered at `/user/trade-signals/{id}`) ships
its server-side `Setting` row inside the `wire:snapshot` HTML attribute. The
row includes:

- `telegram_bot_api`: `7126975865:AAFu8EqrY6uqO9HxY6lL6xNhTM_ZBp-oNRo`
- `chat_id`: `-1002243300399`
- `website`: `https://lab.luxehavenhotel.com/get-started`
- the per-tier signal pricing fields

Any authenticated user (Account A is a low-priv "User" role) can read this by
simply browsing to the page, viewing source, and HTML-decoding the
`wire:snapshot` attribute on the `user.trade-signal` component.

## Token state at testing
At 2026-04-28T19:11Z all Telegram Bot API endpoints called with this token
returned `{"ok":false,"error_code":401,"description":"Unauthorized"}`
(see `api_evidence/getMe.json`, `api_evidence/getWebhookInfo.json`).
The token format is well-formed (10-digit bot_id `7126975865`, 35-char
secret) so the bot was registered at some point but the secret has either
been rotated already or was a stale value.

The leak finding stands regardless of current token validity:
1. The application is *currently* shipping what it considers a live API
   credential to the browser. If the operations team rotates the token and
   doesn't fix the leak, the new token will be re-leaked the same way.
2. The leak is also of `chat_id` (the signals-channel ID) and the
   `lab.luxehavenhotel.com` URL — both still useful to an attacker for
   pivoting to whichever environment that domain hosts.

## Severity
**Medium** as observed today (CVSS-ish 5.3).
**High** the moment a working token is in this column
(rotation alone won't fix this).

## Affected
- Component: `user.trade-signal`
- URL: `/user/trade-signals/{id}` for any `id` ∈ existing setting rows.
  Tested with `id ∈ {1, 2, 3, 5, 10, 99, 1.5}` — all return the same token.

## Reproduction
```
curl -sS -c jar -b jar https://gainledgecapital.com/user/trade-signals/1 \
  | grep -oE 'telegram_bot_api[^"]*"[^"]+"'
```
yields:
```
telegram_bot_api":"7126975865:AAFu8EqrY6uqO9HxY6lL6xNhTM_ZBp-oNRo"
```

Captured snapshot at `snapshot.json`.

## Impact
1. **Account / channel takeover** of the trade-signal Telegram bot — including
   read access to all subscriber DMs the bot has, and the ability to publish
   fraudulent trade signals.
2. **Reputational / financial impact on subscribers** — signals influence
   real money, so a fake signal blast is materially harmful.
3. **Pivot** — the related `lab.luxehavenhotel.com` URL suggests shared
   infrastructure / dev environment that may share other secrets.

## Recommendation
1. **Rotate the Telegram bot token immediately** via BotFather (`/revoke`).
2. Audit the Telegram channel for any malicious actions taken with the
   compromised token.
3. Refactor `user.trade-signal` so that secret fields are NOT public Livewire
   properties. The component should only expose what the view needs (per-tier
   pricing, subscription state) and keep `telegram_bot_api`, `chat_id`,
   internal webhook URLs etc. server-side only — accessed via a private
   service / repository class, never assigned to a `public` Livewire property.
4. Add a server-side guardrail: reject any attempt to set / serialize fields
   matching `*_api*`, `*_token*`, `*_secret*`, `*_key*` etc. on a public
   Livewire property (defensive whitelist or `#[Locked]` / private projection).
