#!/usr/bin/env python3
"""
Lium/Vast profit model. Pulls live Vast VM-capable, Lium-viable offers and
projects monthly margin under two strategies, so you can size the opportunity
and pick the best deals.

Strategies:
  * 8x FLAT on-demand box  -> safe (no interruption -> no Lium slashing),
                              biggest $/Lium-spot, no bid controller needed.
  * 1x DYNAMIC-bid node    -> idle bid = spot floor, spike to on-demand while
                              rented; extra margin but carries slash risk.

Income model: Lium pays its per-GPU reward per online hour (an idle floor;
utilization by real renters is upside only if Lium pays more when rented --
VERIFY THIS, it's the biggest unknown). We treat reward as flat.

  margin/gpu/hr(flat)    = reward - on_demand_price
  margin/gpu/hr(dynamic) = reward - ((1-UTIL)*spot_floor + UTIL*on_demand)
  monthly/gpu            = margin/gpu/hr * 730 * UPTIME

Tune the assumptions below.
"""
import lium_vast_tracker as t

UPTIME = 0.95   # fraction of hours the node is online/earning
UTIL   = 0.30   # fraction of online hours a renter actually holds the GPU
HRS    = 730 * UPTIME


def dyn_cost(r):
    return (1 - UTIL) * r["interruptible_pg"] + UTIL * r["ondemand_pg"]


def main():
    offers = t.fetch_offers()
    v = [r for r in t.evaluate(offers, "ondemand", -99, True) if r["viable"]]

    eights = sorted((r for r in v if r["n"] == 8 and r["m_ondemand"] > 0),
                    key=lambda r: -r["m_ondemand"])
    ones = sorted((r for r in v if r["n"] == 1 and r["m_ondemand"] > 0),
                  key=lambda r: -(r["reward"] - dyn_cost(r)))

    print(f"assumptions: uptime={UPTIME}  util={UTIL}  billable_hrs/mo={HRS:.0f}\n")

    print("== 8x FLAT on-demand boxes (safe, best $/Lium-spot) ==")
    box_total = 0
    for r in eights:
        m = r["m_ondemand"] * 8 * HRS
        box_total += m
        print(f"  8x {r['gpu']:<9} +${r['m_ondemand']:.3f}/gpu -> ${m:,.0f}/mo/box  "
              f"rel {r['rel']:.2f} #{r['id']} {r['geo']}")
    print(f"  -> {len(eights)} boxes, take-all ceiling: ${box_total:,.0f}/mo\n")

    print("== 1x DYNAMIC-bid nodes (extra margin, slash risk) ==")
    one_total = 0
    for r in ones[:10]:
        m = (r["reward"] - dyn_cost(r)) * HRS
        one_total_all = sum((x["reward"] - dyn_cost(x)) * HRS for x in ones)
        print(f"  1x {r['gpu']:<9} +${r['reward']-dyn_cost(r):.3f}/hr -> ${m:,.0f}/mo/node  "
              f"#{r['id']} {r['geo']}")
    one_total = sum((x["reward"] - dyn_cost(x)) * HRS for x in ones)
    print(f"  -> {len(ones)} nodes, take-all ceiling: ${one_total:,.0f}/mo\n")

    print(f"== TOTAL current-supply ceiling (gross): ${box_total+one_total:,.0f}/mo ==")
    print("   Real take-home is lower: capped by Lium open spots + your capital,")
    print("   minus slashing, Bittensor/withdraw fees, and TAO price risk.")
    print("   And ALL of it assumes Lium pays the reward on idle -- verify first.")


if __name__ == "__main__":
    main()
