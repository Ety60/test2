# Finding 06 — `status` is a public Livewire property on the KYC form

## Summary
The component `user.kyc.form` (rendered at `/user/kyc/submit`) declares
`public string $status = "under review";` and serialises it into the
`wire:snapshot` data block. The wire protocol therefore accepts
`updates: {"status": "approved"}` from any authenticated user, which mutates
the property to `"approved"` — including in a subsequent `submit()` call.

I did **not** complete a destructive end-to-end PoC (the `submit()` action
validates 11 mandatory fields including 2 image uploads, and writing a
KYC record on my own account would have been an account-state mutation
covered by the engagement's "no destructive actions without explicit
confirmation" rule).

What I did confirm:

1. `status` is a settable public Livewire property (HTTP 200, snapshot
   shows `status: approved` after the update).
2. The validation rules surfaced by `submit()` with empty fields are:
   `first_name, last_name, email, phone_number, dob, address, city, state,
   country, frontImg, backImg` — **`status` is NOT among the validated
   fields**.
3. There is no obvious server-side guard removing `status` from `$this->all()`
   between mutation and persistence.

If `submit()` calls something like `Kyc::create($this->all())` or
`Kyc::create($this->only([...lots of fields including status]))`, then a
user who fills in the form with bogus-but-non-empty data and uploads any
two images can persist `status='approved'` on first submission, fully
bypassing manual review.

## Severity
**Medium** if the persistence assumption above holds (would be **High** if
KYC unlocks higher withdrawal limits / new privileges) — **Informational**
otherwise, treated as a structural smell.

## Affected
- Component: `user.kyc.form`
- Method: `submit()`
- File on the server (per the debug 500 traces): under
  `/home/gainledg/public_html/app/Livewire/User/Kyc/Form.php` (path
  inferred from class naming convention).

## Reproduction (non-destructive partial)
```
# Fetch fresh CSRF + snapshot of user.kyc.form, then:
POST /livewire/update
{
  "_token": "<csrf>",
  "components": [{
    "snapshot": "<wire:snapshot>",
    "updates": {"status": "approved"},
    "calls": [{"path":"","method":"submit","params":[]}]
  }]
}
```
Response (HTTP 200) shows `memo.errors` enumerates all required fields
**but `status` is no longer "under review" — it is now "approved"** in the
returned snapshot data.

## Recommendation
1. Mark `$status` as `#[Locked]` (Livewire 3) or make it private and expose
   via a getter — never let the client write to a status property.
2. In `submit()`, build the array to persist explicitly:
   ```php
   $kyc = Kyc::create([
     'user_id' => auth()->id(),
     'first_name' => $this->first_name,
     // ... only the fields the user is allowed to set ...
     'status' => 'under review', // never read $this->status here
   ]);
   ```
3. Verify the same pattern across all "create / submit" Livewire components:
   `user.contact-support.send`, `user.fund-transfer.transfer`,
   `user.withdrawal.choose-withdraw-method.requestWithdrawal(...)`,
   `user.investment-plan.buy-a-plan.joinPlan`, and the bank/crypto-address
   `saveWithdrawalMethod` on `user.account-settings.show`.
