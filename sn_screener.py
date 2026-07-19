#!/usr/bin/env python3
"""
sn_screener.py — Bittensor subnet screener for mining opportunity.

Finds subnets with (a) high TAO emission flowing in, and (b) few genuine
competing miners — while explicitly guarding against "king of the hill"
(winner-take-all) payout structures that *look* empty in a snapshot but are
actually the most crowded subnets on the network.

Data source: the chain itself, via the Bittensor SDK. No API key needed.
  - live state:    wss://entrypoint-finney.opentensor.ai:443
  - history:       wss://archive.chain.opentensor.ai:443   (free public archive)

Install:
    pip install bittensor          # v11 (current) — supported
    # legacy v9/v10 also work: pip install "bittensor>=9,<11"

Usage:
    Edit the CONFIG block below, then:  python sn_screener.py

    Pass 1 — leave HISTORY_DAYS = 0. Fast snapshot screen over every subnet,
             using concentration heuristics to guess at king-of-the-hill.
    Pass 2 — set HISTORY_DAYS = 7 and put the shortlist in NETUIDS. Samples
             historical metagraphs to get the *union* of paid miners, which is
             what actually defeats king-of-the-hill. Slow; hence the shortlist.

Output: ranked table to stdout + subnets.csv + subnets.json
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Iterable, Sequence

BLOCKS_PER_DAY = 7200          # 12s blocks
FINNEY = "wss://entrypoint-finney.opentensor.ai:443"
ARCHIVE = "wss://archive.chain.opentensor.ai:443"

# A UID counts as "paid" if its per-block emission exceeds this many alpha.
# 1e-9 alpha/block ~= 7.2e-6 alpha/day, i.e. effectively dust.
PAID_EPS = 1e-9


# ==========================================================================
# CONFIG — edit these, then just run the file.
# ==========================================================================

RPC = FINNEY          # live chain state
ARCHIVE_RPC = ARCHIVE # historical blocks; only used if HISTORY_DAYS > 0

# --- history sampling (the king-of-the-hill killer) -----------------------
# 0.0  = snapshot only, fast, covers every subnet.
# 7.0  = walk back a week of epochs and union the paid-UID sets. Slow.
HISTORY_DAYS = 7.0

# Sample every Nth tempo. 1 = every epoch (most accurate, slowest).
HISTORY_STEP_TEMPOS = 6

# Which subnets to sample history for.
#   []          -> auto-pick: of the 40 richest subnets, the 15 that LOOK
#                  emptiest by naive paid-miner count. Those are exactly the
#                  ones most likely to be KotH traps, so they're what you
#                  actually want verified.
#   [4, 64, 51] -> only these.
NETUIDS: list[int] = [15, 44, 67, 114, 38, 8, 82, 68, 34]

# --- filtering / output ---------------------------------------------------
MIN_TAO_DAY = 0.0     # drop subnets emitting less than this many TAO/day
TOP = 30              # rows printed to stdout (CSV/JSON always get everything)
OUT_PREFIX = "subnets"

# ==========================================================================


# --------------------------------------------------------------------------
# normalisation helpers — the SDK returns Balance objects in some versions,
# raw rao ints in others. Never trust the type.
# --------------------------------------------------------------------------

def f(x: Any) -> float:
    """Coerce Balance | int(rao) | float -> float in the value's OWN units.

    v11's Balance is unit-aware: `.tao` raises UnitMismatchError on an alpha
    balance, and because that is not an AttributeError, `hasattr(x, "tao")`
    raises rather than returning False. So never probe with hasattr here.

    `.amount` is the unit-agnostic accessor (TAO for netuid 0, else that
    subnet's alpha) and is exactly what we want: miner emission stays in
    alpha, subnet emission stays in TAO, and we convert between them
    explicitly via the pool price rather than implicitly here.
    """
    if x is None:
        return 0.0
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        # Bare ints from the runtime are rao; floats are already whole units.
        if isinstance(x, int):
            return x / 1e9 if abs(x) > 1e6 else float(x)
        return float(x)

    for attr in ("amount", "rao", "tao"):          # v11, then legacy, then old
        try:
            v = getattr(x, attr)
        except Exception:                          # noqa: BLE001 — unit errors
            continue
        if v is None:
            continue
        try:
            return float(v) / 1e9 if attr == "rao" else float(v)
        except (TypeError, ValueError):
            continue

    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def farr(xs: Iterable[Any]) -> list[float]:
    return [f(x) for x in (xs or [])]


def gini(xs: Sequence[float]) -> float:
    """Gini coefficient of a non-negative distribution. 0 = flat, 1 = one winner."""
    v = sorted(x for x in xs if x > 0)
    n = len(v)
    if n == 0:
        return 0.0
    if n == 1:
        return 1.0
    total = sum(v)
    if total <= 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(v))
    return (2 * cum) / (n * total) - (n + 1) / n


def hhi(xs: Sequence[float]) -> float:
    """Herfindahl index of emission shares. 1.0 = pure monopoly."""
    total = sum(x for x in xs if x > 0)
    if total <= 0:
        return 0.0
    return sum((x / total) ** 2 for x in xs if x > 0)


def effective_n(xs: Sequence[float]) -> float:
    """Inverse HHI: 'how many miners are really sharing this pie'.

    This is the single most useful number in the whole script. A subnet
    paying 200 UIDs where one takes 95% has effective_n ~= 1.1, not 200.
    """
    h = hhi(xs)
    return (1.0 / h) if h > 0 else 0.0


# --------------------------------------------------------------------------

@dataclass
class SubnetRow:
    netuid: int
    name: str = ""
    symbol: str = ""

    # --- reward side ---
    tao_in_per_day: float = 0.0        # TAO/day injected into the subnet pool
    alpha_out_per_day: float = 0.0     # alpha/day emitted to participants
    emission_share: float = 0.0        # this subnet's share of network emission
    alpha_price_tao: float = 0.0
    miner_tao_per_day: float = 0.0     # ~41% of alpha_out, marked at pool price
    miner_tao_realizable: float = 0.0  # ~41% of actual TAO inflow — the honest one
    emission_live: bool = True         # False when no TAO is flowing in at all

    # --- competition side (snapshot) ---
    max_uids: int = 0
    n_uids: int = 0
    n_miner_uids: int = 0              # dividends == 0, excl. owner
    n_paid_miners: int = 0             # emission > eps  <-- naive answer
    n_serving_miners: int = 0          # axon endpoint published = machine online
    n_weightsetting: int = 0           # `active` flag; validators only, diagnostic
    n_ranked_miners: int = 0           # non-zero rank/trust: validators SEE them

    # --- king-of-the-hill detection ---
    top1_share: float = 0.0            # top miner's share of miner emission
    top5_share: float = 0.0
    miner_gini: float = 0.0
    effective_miners: float = 0.0      # 1/HHI — the honest "how many winners"
    wta_score: float = 0.0             # 0..1, higher = more winner-take-all
    wta_flag: bool = False

    # --- churn / cost ---
    burn_tao: float = 0.0              # recycle cost to register a UID
    regs_last_7d: int = 0
    immunity_period: int = 0
    tempo: int = 0

    # --- history (only if --history-days) ---
    hist_samples: int = 0
    hist_union_paid: int = 0           # UIDs paid at ANY point in window
    hist_mean_paid: float = 0.0        # mean paid-per-snapshot
    rotation_ratio: float = 0.0        # union / mean  -> >2 means winner rotates

    # --- final ---
    competitors: float = 0.0           # best estimate of real competition
    tao_per_competitor: float = 0.0
    tao_per_paid: float = 0.0          # optimistic: only current earners count
    score: float = 0.0
    notes: list[str] = field(default_factory=list)


def build_row(mg: Any, price_tao: float = 0.0) -> SubnetRow:
    """Turn one MetagraphInfo into a screener row."""
    netuid = int(mg.netuid)
    r = SubnetRow(netuid=netuid)
    r.name = str(getattr(mg, "name", "") or "")
    r.symbol = str(getattr(mg, "symbol", "") or "")
    r.tempo = int(getattr(mg, "tempo", 0) or 0)
    r.immunity_period = int(getattr(mg, "immunity_period", 0) or 0)
    r.max_uids = int(getattr(mg, "max_uids", 0) or 0)

    emission = farr(getattr(mg, "emission", []))          # alpha/block per UID
    dividends = farr(getattr(mg, "dividends", []))
    incentive = farr(getattr(mg, "incentive", []))
    rank = farr(getattr(mg, "rank", []))
    trust = farr(getattr(mg, "trust", []))
    active = list(getattr(mg, "active", []) or [])
    hotkeys = list(getattr(mg, "hotkeys", []) or [])
    axons = list(getattr(mg, "axons", []) or [])
    reg_blocks = [int(b) for b in (getattr(mg, "block_at_registration", []) or [])]

    r.n_uids = len(hotkeys) or len(emission)

    # ---- reward side ----
    r.tao_in_per_day = f(getattr(mg, "tao_in_emission", 0)) * BLOCKS_PER_DAY
    r.alpha_out_per_day = f(getattr(mg, "alpha_out_emission", 0)) * BLOCKS_PER_DAY
    r.burn_tao = f(getattr(mg, "burn", 0))

    alpha_in = f(getattr(mg, "alpha_in", 0))
    tao_in = f(getattr(mg, "tao_in", 0))
    r.alpha_price_tao = (tao_in / alpha_in) if alpha_in > 0 else (price_tao or 0.0)
    # miners take ~41% of alpha_out under the standard 18/41/41 split
    r.miner_tao_per_day = 0.41 * r.alpha_out_per_day * r.alpha_price_tao
    # ...but alpha can only be sold into the pool, and the pool is only fed by
    # tao_in_emission. Marking alpha at spot assumes you can exit at spot, which
    # you cannot at size. This is the cash-flow-backed version.
    r.miner_tao_realizable = 0.41 * r.tao_in_per_day
    r.emission_live = r.tao_in_per_day > 1e-9

    # ---- who is a miner ----
    owner_hk = getattr(mg, "owner_hotkey", None)
    miner_idx: list[int] = []
    for i in range(r.n_uids):
        if i < len(dividends) and dividends[i] > 1e-12:
            continue                                   # earns dividends -> validator
        if owner_hk and i < len(hotkeys) and hotkeys[i] == owner_hk:
            continue                                   # subnet owner cut
        miner_idx.append(i)
    r.n_miner_uids = len(miner_idx)

    m_emis = [emission[i] for i in miner_idx if i < len(emission)]
    r.n_paid_miners = sum(1 for e in m_emis if e > PAID_EPS)

    def serving(i: int) -> bool:
        if i >= len(axons):
            return False
        ip = getattr(axons[i], "ip", 0)
        try:
            return int(ip) != 0
        except (TypeError, ValueError):
            return bool(ip)

    # Liveness independent of payout — the key WTA-proof signal.
    # NB: do NOT gate this on the `active` flag. `active` derives from
    # LastUpdate, which subtensor only bumps on set_weights, and miners never
    # set weights. It is a validator-liveness flag; using it here zeroes the
    # column. A published axon means a machine is up and paying for itself.
    r.n_serving_miners = sum(1 for i in miner_idx if serving(i))
    r.n_weightsetting = sum(
        1 for i in miner_idx if i < len(active) and bool(active[i])
    )
    r.n_ranked_miners = sum(
        1 for i in miner_idx
        if (i < len(rank) and rank[i] > 0) or (i < len(trust) and trust[i] > 0)
        or (i < len(incentive) and incentive[i] > 0)
    )

    # ---- concentration ----
    tot = sum(m_emis)
    if tot > 0:
        srt = sorted(m_emis, reverse=True)
        r.top1_share = srt[0] / tot
        r.top5_share = sum(srt[:5]) / tot
    r.miner_gini = gini(m_emis)
    r.effective_miners = effective_n(m_emis)

    # ---- churn ----
    if reg_blocks:
        newest = max(reg_blocks)
        cutoff = newest - 7 * BLOCKS_PER_DAY
        r.regs_last_7d = sum(1 for b in reg_blocks if b >= cutoff)

    return r


def classify_wta(r: SubnetRow) -> None:
    """Decide whether a thin-looking subnet is actually winner-take-all.

    The trap: a KotH subnet pays 1-3 UIDs per tempo, so `n_paid_miners` reads
    like 2 while 200 machines are grinding for that slot. Three independent
    tells, any of which is damning:

      1. Concentration: top1 emission share is huge...
      2. ...but liveness is not: many UIDs are online and being scored.
      3. History: the *identity* of the paid UID rotates between tempos.
    """
    tells = []

    conc = 0.0
    if r.n_paid_miners > 0 and r.n_serving_miners > 0:
        # lots of live miners, almost none paid
        ratio = r.n_paid_miners / max(r.n_serving_miners, 1)
        if ratio < 0.25:
            conc = 1.0 - ratio
            tells.append(f"only {r.n_paid_miners}/{r.n_serving_miners} serving miners paid")

    if r.top1_share > 0.40:
        conc = max(conc, r.top1_share)
        tells.append(f"top-1 takes {r.top1_share:.0%} of miner emission")

    if r.n_ranked_miners > 4 * max(r.n_paid_miners, 1):
        conc = max(conc, 0.8)
        tells.append(f"{r.n_ranked_miners} miners scored but {r.n_paid_miners} paid")

    if r.hist_samples > 1 and r.rotation_ratio > 2.0:
        conc = max(conc, 0.95)
        tells.append(
            f"paid set rotates: {r.hist_union_paid} distinct winners over window "
            f"vs {r.hist_mean_paid:.1f} per snapshot"
        )

    r.wta_score = round(min(conc, 1.0), 3)
    r.wta_flag = r.wta_score >= 0.6
    r.notes.extend(tells)


def finalise(r: SubnetRow) -> None:
    """Pick the honest competitor count and score the opportunity."""
    candidates = [
        r.hist_union_paid if r.hist_samples > 1 else 0,
        # Every registered miner UID is someone who burned TAO for that slot.
        # This is the only competitor signal that is transport-agnostic: a lot
        # of subnets never publish axons (validators reach miners by commitment
        # or off-chain), so an axon count of 6 on a 250-UID subnet means "no
        # axon transport", not "6 competitors".
        r.n_miner_uids,
        r.n_serving_miners,
        r.n_ranked_miners,
        r.n_paid_miners,
        r.effective_miners,
    ]
    # Real competition is the WORST case, not the friendliest one.
    r.competitors = float(max(candidates))
    # Income per competitor. Use the cash-flow-backed figure, not spot-marked
    # alpha: several subnets emit alpha while receiving no TAO at all, which
    # makes the mark-to-market number pure fiction.
    income = min(r.miner_tao_per_day, r.miner_tao_realizable)
    if r.competitors <= 0:
        r.competitors = 0.0
        r.tao_per_competitor = 0.0
    else:
        r.tao_per_competitor = income / r.competitors
    # Optimistic bound: what you'd earn if only the currently-paid miners
    # really compete. True answer sits between this and tao_per_competitor;
    # the history/rotation test is what tells you where.
    r.tao_per_paid = income / max(r.n_paid_miners, 1)

    # Score: reward per competitor, penalised for WTA (variance you can't bank)
    # and for registration cost (capital at risk before first payout).
    base = r.tao_per_competitor
    wta_penalty = 1.0 - 0.85 * r.wta_score
    churn_penalty = 1.0 / (1.0 + r.regs_last_7d / max(r.max_uids or 256, 1) * 4)
    r.score = base * wta_penalty * churn_penalty

    if r.n_miner_uids >= 20 and r.n_serving_miners < 0.05 * r.n_miner_uids:
        r.notes.append(
            f"no axon transport ({r.n_serving_miners}/{r.n_miner_uids} publish "
            "an axon) — 'serve' is not a competition signal here")
    if not r.emission_live:
        r.notes.append("NO TAO INFLOW — emission disabled or not started; "
                       "alpha income is unbacked")
        r.score = 0.0
    if r.miner_tao_per_day > 2 * max(r.miner_tao_realizable, 1e-9):
        r.notes.append(
            f"spot-marked income {r.miner_tao_per_day:.1f} is "
            f"{r.miner_tao_per_day / max(r.miner_tao_realizable, 1e-9):.1f}x "
            "the TAO actually flowing in — exit liquidity is the binding constraint")
    if r.n_paid_miners == 0 and r.miner_tao_per_day > 0:
        r.notes.append("ZERO paid miners — check if subnet is halted/deregistered")
    if r.burn_tao > 0:
        r.notes.append(f"registration burn {r.burn_tao:.2f} TAO")


# --------------------------------------------------------------------------
# chain access
# --------------------------------------------------------------------------

def sdk_major() -> int:
    import bittensor as bt
    try:
        return int(str(getattr(bt, "__version__", "0")).split(".")[0])
    except (ValueError, IndexError):
        return 0


class V11Shim:
    """Adapts a v11 typed Metagraph to the array-shaped view build_row expects.

    v11 restructured everything: per-neuron scores moved onto MetagraphNeuron
    objects (already normalised to 0..1, emission as Balance), while the
    subnet-level pool and emission figures stay in the raw runtime dict under
    the SAME key names v9/v10 used. So we pull from both and flatten.

    Everything below is converted to plain floats in whole-token units here,
    so f() never has to guess whether a bare int is rao.
    """

    def __init__(self, mg: Any):
        raw = dict(getattr(mg, "raw", None) or {})
        neurons = list(getattr(mg, "neurons", None) or [])
        neurons.sort(key=lambda n: int(getattr(n, "uid", 0)))

        self.netuid = int(mg.netuid)
        self.name = getattr(mg, "name", "") or ""
        self.symbol = getattr(mg, "symbol", "") or ""
        self.tempo = int(getattr(mg, "tempo", 0) or 0)
        self.max_uids = int(getattr(mg, "max_uids", 0) or 0)
        self.owner_hotkey = getattr(mg, "owner_hotkey", None)
        self.immunity_period = int(raw.get("immunity_period") or 0)

        def rao(key: str) -> float:
            try:
                return int(raw.get(key) or 0) / 1e9
            except (TypeError, ValueError):
                return 0.0

        self.tao_in_emission = rao("tao_in_emission")
        self.alpha_out_emission = rao("alpha_out_emission")
        self.alpha_in = rao("alpha_in")
        self.tao_in = rao("tao_in")
        self.burn = rao("burn")

        self.hotkeys = [getattr(n, "hotkey", "") for n in neurons]
        self.emission = [f(getattr(n, "emission", 0)) for n in neurons]
        self.dividends = [float(getattr(n, "dividends", 0) or 0) for n in neurons]
        self.incentive = [float(getattr(n, "incentive", 0) or 0) for n in neurons]
        self.rank = [float(getattr(n, "rank", 0) or 0) for n in neurons]
        self.trust = [float(getattr(n, "trust", 0) or 0) for n in neurons]
        self.active = [bool(getattr(n, "active", False)) for n in neurons]
        self.block_at_registration = [
            int(getattr(n, "block_at_registration", 0) or 0) for n in neurons
        ]
        # v11 gives the axon as an "ip:port" string (or None) instead of a struct
        self.axons = [_AxonShim(getattr(n, "axon", None)) for n in neurons]


class _AxonShim:
    """Presents a v11 axon string as something with an .ip attribute."""

    def __init__(self, endpoint: Any):
        self.endpoint = endpoint
        self.ip = 0
        if endpoint:
            host = str(endpoint).rsplit(":", 1)[0].strip("[]")
            if host and host not in ("0.0.0.0", "::", "0"):
                self.ip = 1        # truthy: something is actually being served


def fetch_live(rpc: str) -> list[Any]:
    import bittensor as bt

    if sdk_major() >= 11:
        sub = bt.Subtensor(network=rpc)
        infos = sub.subnets.all()
        netuids = sorted(int(i.netuid) for i in infos)
        print(f"  v11 SDK: pulling {len(netuids)} metagraphs one at a time "
              f"(no bulk call in v11, this takes a minute)", file=sys.stderr)
        out = []
        for netuid in netuids:
            try:
                mg = sub.subnets.metagraph(netuid, commitments=False)
            except Exception as e:                       # noqa: BLE001
                print(f"  [sn{netuid}] {e}", file=sys.stderr)
                continue
            if mg is not None:
                out.append(V11Shim(mg))
        return out

    # ---- legacy v9 / v10 ----
    sub = bt.Subtensor(network=rpc)
    if hasattr(sub, "get_all_metagraphs_info"):
        return sub.get_all_metagraphs_info()
    for lister in ("get_all_subnet_netuids", "get_subnets"):
        if hasattr(sub, lister):
            return [sub.get_metagraph_info(netuid=n) for n in getattr(sub, lister)()]
    raise RuntimeError(
        f"cannot enumerate subnets on bittensor {getattr(bt, '__version__', '?')}; "
        "either upgrade to v11 or pin with: pip install 'bittensor>=9,<11'"
    )


def _paid_uids(mg: Any) -> set[int]:
    """UIDs that received non-dust emission and are not earning dividends."""
    emission = farr(getattr(mg, "emission", []))
    dividends = farr(getattr(mg, "dividends", []))
    return {
        i for i, e in enumerate(emission)
        if e > PAID_EPS and (i >= len(dividends) or dividends[i] <= 1e-12)
    }


def fetch_history(rpc: str, netuids: list[int], days: float, step_tempos: int,
                  tempos: dict[int, int]) -> dict[int, dict]:
    """Sample historical metagraphs from the archive node.

    For each subnet we walk backwards one tempo at a time and record WHICH
    UIDs were paid at each epoch. The union over the window is the real
    number of miners earning on that subnet; the per-snapshot mean is what a
    naive screener would have reported. union/mean is the rotation ratio.
    """
    import bittensor as bt

    v11 = sdk_major() >= 11
    sub = (bt.Subtensor(network=rpc, archive_endpoints=[rpc]) if v11
           else bt.Subtensor(network=rpc))
    # v11 11.0.0: Subtensor.block is a *method*, not a property — int() on the
    # bound method raises TypeError. Call it if callable; tolerate either form.
    if v11:
        _blk = sub.block
        head = int(_blk() if callable(_blk) else _blk)
    else:
        head = sub.get_current_block()

    def at_block(netuid: int, block: int) -> Any:
        if v11:
            mg = sub.subnets.metagraph(netuid, block=block, commitments=False)
            return V11Shim(mg) if mg is not None else None
        return sub.get_metagraph_info(netuid=netuid, block=block)

    out: dict[int, dict] = {}
    for netuid in netuids:
        tempo = max(tempos.get(netuid, 360), 1)
        step = tempo * max(step_tempos, 1)
        n_steps = max(int(days * BLOCKS_PER_DAY / step), 1)
        union: set[int] = set()
        per_snap: list[int] = []
        for k in range(n_steps):
            block = head - k * step
            if block < 1:
                break
            try:
                mg = at_block(netuid, block)
            except Exception as e:              # noqa: BLE001
                print(f"  [sn{netuid}] block {block}: {e}", file=sys.stderr)
                continue
            if mg is None:
                continue
            paid = _paid_uids(mg)
            union |= paid
            per_snap.append(len(paid))
            time.sleep(0.05)
        mean = (sum(per_snap) / len(per_snap)) if per_snap else 0.0
        out[netuid] = {
            "samples": len(per_snap),
            "union": len(union),
            "mean": mean,
            "rotation": (len(union) / mean) if mean > 0 else 0.0,
        }
        print(f"  sn{netuid:<4} samples={len(per_snap):<4} union={len(union):<4} "
              f"mean={mean:<6.1f} rotation={out[netuid]['rotation']:.2f}",
              file=sys.stderr)
    return out


# --------------------------------------------------------------------------

def main() -> int:
    print(f"connecting to {RPC} ...", file=sys.stderr)
    mgs = fetch_live(RPC)
    print(f"got {len(mgs)} subnets", file=sys.stderr)

    rows = [build_row(mg) for mg in mgs]
    rows = [r for r in rows if r.netuid != 0]            # root is not minable
    tempos = {r.netuid: (r.tempo or 360) for r in rows}

    if HISTORY_DAYS > 0:
        if NETUIDS:
            want = list(NETUIDS)
        else:
            # default: the subnets that a snapshot screen would flag as
            # "empty and rich" — exactly the ones most likely to be KotH traps
            ranked = sorted(rows, key=lambda r: -r.tao_in_per_day)[:40]
            want = [r.netuid for r in sorted(ranked, key=lambda r: r.n_paid_miners)[:15]]
        print(f"sampling history for netuids {want} ...", file=sys.stderr)
        hist = fetch_history(ARCHIVE_RPC, want, HISTORY_DAYS,
                             HISTORY_STEP_TEMPOS, tempos)
        by_id = {r.netuid: r for r in rows}
        for netuid, h in hist.items():
            r = by_id[netuid]
            r.hist_samples = h["samples"]
            r.hist_union_paid = h["union"]
            r.hist_mean_paid = h["mean"]
            r.rotation_ratio = h["rotation"]

    for r in rows:
        classify_wta(r)
        finalise(r)

    rows = [r for r in rows if r.tao_in_per_day >= MIN_TAO_DAY]
    rows.sort(key=lambda r: -r.score)
    if not rows:
        print("no subnets passed MIN_TAO_DAY filter", file=sys.stderr)
        return 1

    hdr = (f"{'net':>4} {'name':<16} {'TAO/d in':>9} {'real/d':>8} "
           f"{'slots':>6} {'paid':>5} {'serve':>6} {'eff':>6} {'union':>6} "
           f"{'top1':>6} {'WTA':>5} {'t/slot':>8} {'t/paid':>8}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows[:TOP]:
        print(f"{r.netuid:>4} {r.name[:16]:<16} {r.tao_in_per_day:>9.1f} "
              f"{r.miner_tao_realizable:>8.2f} {r.n_miner_uids:>6} "
              f"{r.n_paid_miners:>5} {r.n_serving_miners:>6} "
              f"{r.effective_miners:>6.1f} "
              f"{r.hist_union_paid:>6} {r.top1_share:>6.0%} "
              f"{'YES' if r.wta_flag else '-':>5} "
              f"{r.tao_per_competitor:>8.4f} {r.tao_per_paid:>8.4f}")

    with open(f"{OUT_PREFIX}.json", "w") as fh:
        json.dump([asdict(r) for r in rows], fh, indent=2)

    import csv
    with open(f"{OUT_PREFIX}.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(asdict(rows[0]).keys()))
        w.writeheader()
        for r in rows:
            d = asdict(r)
            d["notes"] = "; ".join(d["notes"])
            w.writerow(d)

    print(f"\nwrote {OUT_PREFIX}.json / {OUT_PREFIX}.csv", file=sys.stderr)
    print("\nRead the WTA column before believing a low 'paid' count.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
