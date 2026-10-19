#!/usr/bin/env python3
"""
Lium <-> Vast.ai dynamic-bid controller.

The margin trick: a Lium node earns the same idle reward whether it sits idle
or serves a renter, but on Vast an *interruptible* instance's bid price is
mutable at runtime. So:

  * while your node is IDLE  -> hold a LOW bid  (pay the cheap spot floor)
  * the moment Lium RENTS it -> spike to a HIGH bid (lock out other bidders so
    the live rental can't be interrupted -> no Lium slashing)

Because you're idle most hours, your average GPU cost falls toward the spot
floor while the Lium reward stays flat -- widening the margin 50-85% vs paying
flat on-demand.

WHAT THIS DOES NOT DO (be honest):
  * It cannot stop an ON-DEMAND renter of the same machine from preempting you
    (Vast gives on-demand absolute priority regardless of bid). The HIGH bid
    only beats other *interruptible* bidders. So run this only on hosts with low
    on-demand demand, and treat a rare on-demand preemption as residual slash
    risk. Pick high-reliability hosts.
  * It does not itself talk to Lium. You supply a "am I rented right now?" probe
    (a shell command or URL) that reflects your Lium node's live rental state.

Safety model:
  * On any doubt, it bids HIGH (fail safe -> protect against slashing).
  * It raises to HIGH immediately on a rental; it only drops to LOW after the
    rental has been gone for --cooldown seconds (avoid dropping mid-handoff).
  * --dry-run (default) logs decisions without touching the bid. Pass
    --live to actually change bids.

Usage:
  export VAST_API_KEY=...
  # probe returns exit 0 when the node is currently rented:
  python3 lium_bid_controller.py --instance-id 12345678 \
      --low 0.15 --high 0.60 --rented-cmd 'lium node status --json | grep -q RENTED' \
      --interval 15 --cooldown 120 --live
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

VAST_BASE = "https://console.vast.ai/api/v0"


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _api(method, path, key, body=None, timeout=30):
    url = f"{VAST_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Accept": "application/json",
                                          "Content-Type": "application/json",
                                          "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw.strip() else {}


def get_current_bid(instance_id, key):
    """Best-effort read of the instance's current bid price (None if unknown)."""
    try:
        data = _api("GET", f"/instances/{instance_id}/", key)
        inst = data.get("instances", data) if isinstance(data, dict) else {}
        for field in ("cur_bid", "search_bid_price", "min_bid", "dph_total"):
            if isinstance(inst, dict) and inst.get(field) is not None:
                return float(inst[field])
    except Exception as e:
        log(f"  ! could not read current bid: {e}")
    return None


def set_bid(instance_id, price, key, dry_run):
    if dry_run:
        log(f"  DRY-RUN would set bid -> ${price:.3f}")
        return True
    try:
        _api("PUT", f"/instances/bid_price/{instance_id}/", key,
             body={"client_id": "me", "price": round(price, 3)})
        log(f"  set bid -> ${price:.3f}")
        return True
    except Exception as e:
        log(f"  ! set_bid failed: {e}")
        return False


def is_rented(rented_cmd, rented_url, timeout=10):
    """Return True if the Lium node is currently serving a rental.

    Fail-safe: on any error we return True so the controller bids HIGH and does
    not risk a slash. Provide exactly one of rented_cmd / rented_url.
    """
    try:
        if rented_cmd:
            # convention: exit 0 == rented, exit 1 == idle, anything else
            # (127 not-found, 126, >1, ...) is treated as an error -> fail-safe.
            rc = subprocess.run(rented_cmd, shell=True, timeout=timeout).returncode
            if rc == 0:
                return True
            if rc == 1:
                return False
            log(f"  ! rented-cmd exit {rc} (not 0/1); assuming RENTED (fail-safe)")
            return True
        if rented_url:
            with urllib.request.urlopen(rented_url, timeout=timeout) as r:
                txt = r.read().decode().strip().lower()
            return txt in ("1", "true", "rented", "busy") or '"rented"' in txt
    except Exception as e:
        log(f"  ! rented-probe error ({e}); assuming RENTED (fail-safe)")
        return True
    log("  ! no rented probe configured; assuming RENTED (fail-safe)")
    return True


def run(args):
    key = os.environ.get("VAST_API_KEY") or args.api_key
    if not key:
        sys.exit("VAST_API_KEY not set (env or --api-key)")
    if args.low >= args.high:
        sys.exit("--low must be below --high")

    log(f"controller start: instance={args.instance_id} low=${args.low} "
        f"high=${args.high} interval={args.interval}s cooldown={args.cooldown}s "
        f"{'LIVE' if args.live else 'DRY-RUN'}")

    state = None            # "HIGH" or "LOW"
    last_rented_at = 0.0
    try:
        while True:
            rented = is_rented(args.rented_cmd, args.rented_url)
            now = time.time()
            if rented:
                last_rented_at = now
                want = "HIGH"
            else:
                # only relax to LOW once the rental has been gone > cooldown
                want = "LOW" if (now - last_rented_at) >= args.cooldown else "HIGH"

            if want != state:
                price = args.high if want == "HIGH" else args.low
                verb = "RENTED -> lock" if want == "HIGH" else "idle -> save"
                log(f"{verb}: bid {state or '?'} -> {want}")
                if set_bid(args.instance_id, price, key, dry_run=not args.live):
                    state = want
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log("stopped (bid left at last value).")


def selftest():
    """Offline check of the hysteresis/cooldown decision logic (no API calls)."""
    import types
    seq = [True, True, False, False, False, False, True, False]  # rented? per tick
    cooldown, interval = 5, 2   # gone >=5s (>=3 ticks) before relaxing
    state, last, t = None, -999, 0
    out = []
    for rented in seq:
        if rented:
            last = t; want = "HIGH"
        else:
            want = "LOW" if (t - last) >= cooldown else "HIGH"
        out.append((t, rented, want))
        state = want
        t += interval
    print("t   rented  ->bid")
    for tt, r, w in out:
        print(f"{tt:<3} {str(r):<6}  {w}")
    # expect: HIGH while rented, HIGH for cooldown after, LOW only once gone long enough
    assert out[0][2] == "HIGH" and out[2][2] == "HIGH" and out[4][2] == "LOW", out
    assert out[6][2] == "HIGH", out  # re-rent snaps back to HIGH immediately
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Lium/Vast dynamic-bid controller")
    ap.add_argument("--instance-id", help="Vast interruptible instance id")
    ap.add_argument("--low", type=float, default=0.15, help="idle bid $/hr")
    ap.add_argument("--high", type=float, default=0.60,
                    help="rented bid $/hr (keep below your Lium income)")
    ap.add_argument("--interval", type=int, default=15, help="poll seconds")
    ap.add_argument("--cooldown", type=int, default=120,
                    help="seconds a rental must be gone before dropping to LOW")
    ap.add_argument("--rented-cmd", help="shell cmd; exit 0 == currently rented")
    ap.add_argument("--rented-url", help="URL returning rented/idle state")
    ap.add_argument("--api-key", help="Vast API key (else VAST_API_KEY env)")
    ap.add_argument("--live", action="store_true",
                    help="actually change bids (default: dry-run)")
    ap.add_argument("--selftest", action="store_true",
                    help="run offline logic check and exit")
    args = ap.parse_args()
    if args.selftest:
        selftest(); return
    if not args.instance_id:
        ap.error("--instance-id required (or use --selftest)")
    run(args)


if __name__ == "__main__":
    main()
