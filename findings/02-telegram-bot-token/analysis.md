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

## Severity
**High** (CVSS-ish 7.5, AV:N/AC:L/PR:L/UI:N/S:C/C:H/I:L/A:N).

A Telegram bot token is a long-lived credential that grants:
- read/send permissions on every chat the bot is in (notably the signals
  channel `-1002243300399`),
- ability to mutate the bot's behaviour (commands, webhooks, name),
- in this app, the bot is used to publish trade signals — an attacker
  controlling the bot can publish fake signals to subscribers and steer
  their trading behaviour, effectively a market-manipulation channel.

The cross-domain `lab.luxehavenhotel.com` reference suggests that staging /
related infrastructure also leaks via this same row.

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
