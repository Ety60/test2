#!/usr/bin/env python3
"""
Lium <-> Vast.ai arbitrage tracker.

Finds Vast.ai GPU offers whose rental price is BELOW what Lium (Bittensor SN51)
pays as a reward for that GPU, so you can run a Lium provider node at a profit.

For every matching offer it reports BOTH price modes:
  - on-demand  (dph_total): the stable price you'd bump to when Lium rents your node
  - interruptible (min_bid): the cheap bid price to run while your node sits idle

Margin = Lium reward $/hr/GPU  -  Vast price $/hr/GPU   (positive == profit)

Lium requires a root VM + Sysbox, a public IP, and open ports (8080/2200), so
the tracker pre-filters offers that clearly can't host a node. It CANNOT verify
VM support from the offer feed alone -- see NOTE_VM below -- so treat surviving
offers as candidates to confirm, not guarantees.

Usage:
    python3 lium_vast_tracker.py                 # one-shot scan
    python3 lium_vast_tracker.py --watch 60      # rescan every 60s, alert on new hits
    python3 lium_vast_tracker.py --mode ondemand # rank by on-demand margin instead
    python3 lium_vast_tracker.py --all           # show every offer, not just profitable
    python3 lium_vast_tracker.py --min-margin 0.05

Optional: set VAST_API_KEY in the environment for higher rate limits.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

VAST_ENDPOINT = "https://console.vast.ai/api/v0/bundles/"

# --- Lium SN51 reward rates ($/hr/GPU). Edit to match the current dashboard. ---
# Each entry: canonical label -> (lium_reward, [substrings that match Vast gpu_name])
# gpu_name matching is case-insensitive substring; first matching rule wins, so
# order from most-specific to least-specific.
LIUM_REWARDS = [
    ("B300",          5.10, ["b300"]),
    ("B200",          4.25, ["b200"]),
    ("H200",          2.85, ["h200"]),
    ("H100",          1.49, ["h100"]),
    ("RTX PRO 6000",  0.86, ["rtx pro 6000", "pro 6000"]),
    ("RTX 6000 Ada",  0.69, ["6000ada", "6000 ada", "rtx 6000-ada"]),
    ("RTX 5090",      0.65, ["5090"]),
    ("L40S",          0.35, ["l40s"]),
    ("L40",           0.36, ["l40"]),
    ("A100",          0.36, ["a100"]),
    ("RTX A6000",     0.32, ["a6000"]),
    ("RTX 4090",      0.30, ["4090"]),
    ("RTX 3090",      0.16, ["3090"]),
]

# Exact Vast `gpu_name` values to query. The feed caps each response at ~64
# offers, so we query per name (cheapest-first) and merge -- that keeps the
# best-margin offers even when a popular card has hundreds of listings.
# Unknown names simply return nothing, so over-listing here is harmless.
VAST_GPU_NAMES = [
    "B200", "B300",
    "H200", "H200 NVL",
    "H100 SXM", "H100 PCIE", "H100 NVL",
    "RTX PRO 6000",
    "RTX 6000Ada",
    "RTX 5090",
    "L40S", "L40",
    "A100 SXM4", "A100 PCIE", "A100 80GB PCIe",
    "RTX A6000",
    "RTX 4090",
    "RTX 3090",
]

# --- Lium node hardware minimums (from docs.lium.io executor requirements) ---
MIN_DISK_GB = 100          # >= 100 GB free
MIN_PORTS = 2              # need at least 8080 + 2200 mappable
MIN_RELIABILITY = 0.90     # skip flaky hosts; a dropped rental costs more than it saves


def reward_for(gpu_name: str):
    """Return (label, reward) for a Vast gpu_name, or (None, None) if unlisted."""
    name = gpu_name.lower()
    for label, reward, needles in LIUM_REWARDS:
        if any(n in name for n in needles):
            return label, reward
    return None, None


def _query(q, timeout):
    url = VAST_ENDPOINT + "?" + urllib.parse.urlencode({"q": json.dumps(q)})
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    key = os.environ.get("VAST_API_KEY")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode()).get("offers", [])


def fetch_offers(verified_only=False, timeout=45):
    """Query the Vast feed once per target GPU name and merge, deduped by id."""
    merged = {}
    for name in VAST_GPU_NAMES:
        q = {
            "gpu_name": {"in": [name]},
            "rentable": {"eq": True},
            "num_gpus": {"gte": 1},
            "order": [["dph_total", "asc"]],  # cheapest first -> best margins survive cap
            "limit": 500,
        }
        if verified_only:
            q["verified"] = {"eq": True}
        for attempt in range(3):
            try:
                for o in _query(q, timeout):
                    merged[o["id"]] = o
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:  # back off and retry on rate limit
                    time.sleep(1.5 * (attempt + 1))
                    continue
                print(f"  ! query for {name!r} failed: {e}", file=sys.stderr)
                break
            except Exception as e:  # one bad GPU name shouldn't kill the whole scan
                print(f"  ! query for {name!r} failed: {e}", file=sys.stderr)
                break
        time.sleep(0.2)  # gentle pacing to stay under the rate limit
    return list(merged.values())


def lium_viable(o):
    """Cheap pre-filter for obvious Lium disqualifiers. Returns (ok, reason)."""
    if not o.get("public_ipaddr"):
        return False, "no public IP"
    if (o.get("direct_port_count") or 0) < MIN_PORTS:
        return False, "too few open ports"
    if (o.get("disk_space") or 0) < MIN_DISK_GB:
        return False, f"disk {o.get('disk_space', 0):.0f}GB < {MIN_DISK_GB}"
    if (o.get("reliability") or 0) < MIN_RELIABILITY:
        return False, f"reliability {o.get('reliability', 0):.2f}"
    return True, ""


def evaluate(offers, mode, min_margin, show_all):
    """Attach margin fields and return the rows we care about, best margin first."""
    rows = []
    for o in offers:
        label, reward = reward_for(o.get("gpu_name", ""))
        if reward is None:
            continue
        n = o.get("num_gpus") or 1
        ondemand_pg = (o.get("dph_total") or 0) / n
        # min_bid is the whole-instance interruptible price; fall back to on-demand.
        interruptible_pg = (o.get("min_bid") or o.get("dph_total") or 0) / n

        m_ondemand = reward - ondemand_pg
        m_interruptible = reward - interruptible_pg
        margin = m_interruptible if mode == "interruptible" else m_ondemand

        ok, reason = lium_viable(o)
        row = {
            "id": o.get("id"),
            "gpu": label,
            "vast_name": o.get("gpu_name"),
            "n": n,
            "reward": reward,
            "ondemand_pg": ondemand_pg,
            "interruptible_pg": interruptible_pg,
            "m_ondemand": m_ondemand,
            "m_interruptible": m_interruptible,
            "margin": margin,
            "total_margin": margin * n,
            "geo": o.get("geolocation") or "?",
            "rel": o.get("reliability") or 0,
            "disk": o.get("disk_space") or 0,
            "verified": o.get("verified", None),
            "viable": ok,
            "reason": reason,
        }
        if not show_all:
            if not ok:
                continue
            if margin < min_margin:
                continue
        rows.append(row)
    rows.sort(key=lambda r: r["margin"], reverse=True)
    return rows


def print_table(rows, mode):
    if not rows:
        print("  (no offers matched)")
        return
    hdr = (f"{'GPU':<14}{'n':>2}  {'reward':>7}  {'on-dem':>7}  {'interr':>7}  "
           f"{'MARGIN':>8}  {'tot/hr':>7}  {'rel':>5}  {'disk':>6}  offer / location")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in rows[: print_table.top or None]:
        flag = "" if r["viable"] else "  [!" + r["reason"] + "]"
        print(f"{r['gpu']:<14}{r['n']:>2}  "
              f"{r['reward']:>6.2f}  {r['ondemand_pg']:>6.3f}  {r['interruptible_pg']:>6.3f}  "
              f"{r['margin']:>+7.3f}  {r['total_margin']:>+6.2f}  "
              f"{r['rel']:>5.2f}  {r['disk']:>5.0f}G  #{r['id']} {r['geo']}{flag}")
    shown = min(len(rows), print_table.top) if print_table.top else len(rows)
    extra = f" (showing top {shown} of {len(rows)}; --top 0 for all)" if shown < len(rows) else ""
    print(f"\n  Ranked by {mode} per-GPU margin. MARGIN>0 == profit. "
          f"'tot/hr' = margin x GPUs on that offer.{extra}")


print_table.top = 25  # rows to print; overridden by --top


def scan(args):
    offers = fetch_offers(verified_only=args.verified)
    rows = evaluate(offers, args.mode, args.min_margin, args.all)
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{stamp}] {len(offers)} offers fetched; "
          f"{len(rows)} shown (mode={args.mode}, min_margin=${args.min_margin:.3f}).")
    print_table(rows, args.mode)
    return {r["id"] for r in rows if r["viable"] and r["margin"] >= args.min_margin}


def main():
    ap = argparse.ArgumentParser(description="Lium/Vast arbitrage tracker")
    ap.add_argument("--mode", choices=["interruptible", "ondemand"],
                    default="interruptible",
                    help="which price to rank/filter by (default: interruptible)")
    ap.add_argument("--min-margin", type=float, default=0.0,
                    help="minimum $/hr/GPU margin to show (default: 0.0)")
    ap.add_argument("--watch", type=int, metavar="SECONDS", default=0,
                    help="rescan every N seconds and alert on newly profitable offers")
    ap.add_argument("--all", action="store_true",
                    help="show every Lium-listed GPU offer, including unprofitable/non-viable")
    ap.add_argument("--verified", action="store_true",
                    help="restrict to Vast 'verified' datacenter hosts")
    ap.add_argument("--top", type=int, default=25,
                    help="max rows to print, 0 = all (default: 25)")
    args = ap.parse_args()
    print_table.top = args.top

    if args.watch <= 0:
        scan(args)
        return

    print(f"Watching Vast every {args.watch}s. Ctrl-C to stop.")
    seen = set()
    try:
        while True:
            current = scan(args)
            new = current - seen
            if new and seen:  # don't alert on the very first populate
                print("\n  *** NEW PROFITABLE OFFER(S): "
                      + ", ".join(f"#{i}" for i in sorted(new)) + " ***")
            seen = current
            time.sleep(args.watch)
    except KeyboardInterrupt:
        print("\nstopped.")


# NOTE_VM: The offers feed does not expose a reliable "supports VM" flag, and Lium
# needs a real root VM (for Sysbox), not a container. Before renting a surviving
# candidate, confirm on the Vast console that the machine offers VM (not just
# Docker) mode and that interruptible pricing is available for that VM -- on many
# hosts spot/bid pricing is container-only.

if __name__ == "__main__":
    main()
