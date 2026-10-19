# Finding 01 — Debug mode (`APP_DEBUG=true`) on production

## Summary
The Laravel application returns full Whoops/Ignition-style debug HTML (with stack
traces and absolute filesystem paths) on any unhandled exception, instead of a
sanitised 500 page. This is `APP_DEBUG=true` in production.

## Severity
**Medium** (CVSS-ish 5.3, AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N).

Authenticated user → information disclosure of file paths and framework versions.
Combined with Livewire's known debug-mode-only exposure
(e.g. CVE-2024-13918 / CVE-2024-13919 cross-site script execution and various
Ignition / Telescope chains), debug mode in production materially increases
the attack surface.

## Affected
- All routes (any unhandled exception).
- Demonstrated by hitting `POST /livewire/update` with an `updates` value that
  triggers a server exception.

## Reproduction
```
# Authenticate first to get a session, then send a Livewire update that
# triggers ModelSynth::set on a model property:
curl -sS -c jar -b jar -X POST https://gainledgecapital.com/livewire/update \
  -H 'Content-Type: application/json' \
  --data-binary @payload.json
```

`payload.json` (built from a fresh wire:snapshot of `user.account-settings.show`):
```
{
  "_token": "<csrf>",
  "components": [{
    "snapshot": "<HTML-decoded snapshot>",
    "updates": {"user.role": "X"},
    "calls": []
  }]
}
```

Response is HTTP 500 with body:
```
Exception: Can't set model properties directly in file
/home/gainledg/public_html/vendor/livewire/livewire/src/Features/SupportModels/ModelSynth.php on line 75
#0 /home/gainledg/public_html/vendor/livewire/livewire/src/...
```

(See `response_user_role_500.html` — first 200 KB captured.)

## Impact
- Discloses absolute server filesystem path: `/home/gainledg/public_html/`
  (suggests cPanel hosting under user `gainledg`).
- Discloses every vendor library used (`livewire/livewire`, exact PHP files
  hit by the request flow).
- A remote attacker that finds another vulnerability can leverage these
  paths in PHP injection, LFI, or path-traversal attacks.

## Recommendation
Set `APP_DEBUG=false` in `.env` on production. Run
`php artisan config:cache` to bake the change. Pair with a sanitised 500
error page (`resources/views/errors/500.blade.php`).
