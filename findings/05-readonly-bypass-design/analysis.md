# Finding 05 — `readonly` HTML attribute is the only protection on identity fields (defence-in-depth)

## Summary
On the profile editor at `/user/account-settings` (component
`user.account-settings.show`), the `email`, `username`, `country`, and
`address` `<input>` elements are marked `readonly` in HTML, but the
underlying Livewire `wire:model` properties are accepting arbitrary updates
from the wire protocol.

I confirmed:
- Sending `updates: {"email": "<another user's email>"}` is **accepted** by
  the server with no validation error and the property is mutated in the
  component snapshot.
- However, the `saveProfile()` method appears to whitelist columns
  server-side: a fresh GET of `/user/account-settings` shows the original
  email persisted (no DB write happened).

So this is **not exploitable today**, but it is a defence-in-depth concern:

1. `readonly` is a UI-only hint. A future contributor adding a wire-model
   field with a `readonly` input may incorrectly assume that the property
   can't be set from the wire protocol and skip server-side validation.
2. The rendering of these properties in the snapshot also makes them visible
   to anyone with the rendered HTML — `email` is *intentionally* revealed
   (the user's own email), but `country` and `address` are similarly bound,
   and tomorrow another developer might bind a sensitive field by accident.
3. There is no `unique:users,email` or `confirmed` rule visible — sending
   `email = <other user's email>` did not return any "already taken" error,
   which would normally leak that other user's existence.

## Severity
**Informational** (no current exploit, but a structural smell that pairs
with future BAC bugs).

## Affected
- Component: `user.account-settings.show`, method `saveProfile`.
- Properties: `email`, `username`, `country`, `address` (and likely the
  bank-details readonly fields if added later).

## Reproduction
```
# 1. Fetch a fresh wire:snapshot from /user/account-settings.
# 2. POST /livewire/update with:
#    updates: {"email": "<account_b_email>"}
#    calls: [{"path":"","method":"saveProfile","params":[]}]
# Response: HTTP 200, snapshot.email is now <account_b_email>, no errors.
# 3. GET /user/account-settings — DB still has the original email
#    (proving the server-side whitelist is what's preventing the takeover).
```

## Recommendation
- Add server-side `validate(['email' => 'required|email|unique:users,email,'.$this->user->id])` for any property whose flow allows updating the user model — even if save logic currently whitelists, the Livewire layer currently lies to the client about field state, which can confuse future maintainers.
- Use Livewire's `#[Locked]` attribute on properties that the server should
  never accept from the client.
- Prefer separate "view-model" properties for read-only display (e.g.
  `public string $emailDisplay`) — never bind a wire:model on a writable
  property the user is not actually allowed to change.
