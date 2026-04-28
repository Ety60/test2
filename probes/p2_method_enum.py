#!/usr/bin/env python3
"""
Probe 3.2 — Public method enumeration. NON-destructive method names only.
Tests each component for unannounced public methods.
"""
import sys, os, time, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lw_send import fresh_component, lw_update

# (jar, page_path, component_name)
COMPONENTS = [
    ("cookies_a.txt", "/user/account-settings", "user.account-settings.show"),
    ("cookies_a.txt", "/user/notifications", "user.notifications"),
    ("cookies_a.txt", "/user/referral", "user.referral"),
    ("cookies_a.txt", "/user/kyc/submit", "user.kyc.form"),
    ("cookies_a.txt", "/user/kyc/start", "user.kyc.info"),
    ("cookies_a.txt", "/user/transfer-fund", "user.fund-transfer"),
    ("cookies_a.txt", "/user/withdraw/request", "user.withdrawal.choose-withdraw-method"),
    ("cookies_a.txt", "/user/investment/buy-plan", "user.investment-plan.buy-a-plan"),
    ("cookies_a.txt", "/user/trade-signals/1", "user.trade-signal.subscribe"),
    ("cookies_a.txt", "/user/copy-trader", None),  # discover dynamically
]

# Read-y / metadata methods only. NO destructive verbs (no delete/destroy/...).
METHODS = [
    "loadUser", "selectUser", "setUserId", "setUser", "viewAs",
    "impersonate", "assumeIdentity", "loginAs", "switchUser",
    "export", "exportCsv", "download", "dump", "downloadAll",
    "refresh", "reload",
    "mountAction", "callMountedAction", "mountTableAction",
    "callAction", "executeAction",
    "render", "boot", "mount",  # framework hooks
    "getUser", "getProfile", "loadProfile",
    "show", "view", "showAll",
    "approve",  # interesting signal
    "verify",   # interesting signal
    "unlock",   # interesting signal
]


def classify(code, body):
    if code == 200:
        return "200 OK (EXISTS)"
    if "Public method" in body and "not found" in body:
        return "method NOT FOUND"
    if "is not allowed" in body or "not authorized" in body.lower():
        return "BLOCKED (exists)"
    if "Argument" in body and "required" in body:
        return "EXISTS (needs args)"
    if "Method " in body and ("not allowed" in body):
        return "BLOCKED"
    return f"HTTP {code}"


os.makedirs("findings/p2_method_enum", exist_ok=True)
results = []
for jar, path, comp in COMPONENTS:
    if comp is None:
        # Try to find the component on the page
        from lw_send import fetch_page
        c, body = fetch_page(jar, path)
        m = re.search(r'wire:snapshot="((?:[^"\\]|\\.)*)"', body)
        if not m:
            print(f"  (no component on {path})"); continue
        try:
            obj = json.loads(__import__('html').unescape(m.group(1)))
            comp = obj["memo"]["name"]
        except Exception:
            print(f"  (no parseable comp on {path})"); continue
    print(f"\n== {comp} ({path}) ==")
    for m in METHODS:
        try:
            csrf, raw, _ = fresh_component(jar, path, comp)
        except Exception as e:
            print(f"  [skip] {e}")
            break
        code, _p, body = lw_update(jar, raw,
            updates={}, calls=[{"path": "", "method": m, "params": []}],
            csrf=csrf, referer="https://gainledgecapital.com" + path,
            save=f"findings/p2_method_enum/{comp.replace('.','_')}__{m}.out")
        cls = classify(code, body)
        results.append({"comp": comp, "method": m, "code": code, "class": cls})
        print(f"  {m:24s}  HTTP {code}  {cls}")
        if "EXISTS" in cls or "BLOCKED" in cls or "200" in cls:
            print(f"      -> {body[:200]}")
        time.sleep(0.4)

with open("findings/p2_method_enum/_summary.json", "w") as f:
    json.dump(results, f, indent=2)
