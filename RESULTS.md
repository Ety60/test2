# Bittensor subnet screener — run results (block 8,656,591, 7-day window)

Goal: best ratio of *real* TAO emission to *genuine* mining competition, guarding
against king-of-the-hill (winner-take-all) subnets that look empty in a snapshot.

## Step 2 (history / rotation) — the deciding pass

| net | name     | TAO/d in | real/d | slots | paid | union | mean | rotation | top1 | WTA | verdict            |
|----:|----------|---------:|-------:|------:|-----:|------:|-----:|---------:|-----:|:---:|--------------------|
| 120 | Affine   |    84.8  |  34.8  |  250  |   5  |    8  |  5.0 |   1.60   | 20%  |  -  | genuinely thin     |
|   4 | Targon   |    57.0  |  23.4  |  250  |   7  |    9  |  7.0 |   1.29   | 25%  |  -  | genuinely thin     |
|  64 | Chutes   |    82.4  |  33.8  |  244  |  18  |   18  | 16.2 |   1.11   | 28%  |  -  | stable, moderate   |
|  51 | lium.io  |    67.8  |  27.8  |  246  |  43  |   47  | 40.4 |   1.16   | 45%  |  -  | stable, crowded    |
|  97 | Albedo   |    95.5  |  39.2  |  254  |   5  |   16  |  5.0 |   3.20   | 20%  | YES | KING-OF-THE-HILL   |
| 107 | Minos    |   135.5  |  55.6  |   82  |  20  |   72  | 19.9 |   3.61   | 90%  | YES | KING-OF-THE-HILL   |
|  96 | Verathos |    40.2  |  16.5  |  250  |  65  |  183  | 75.9 |   2.41   |  5%  | YES | crowded + rotating |

rotation ~1 => paid set stable (t/paid ~ truth); rotation >2 => winner rotates,
subnet is crowded regardless of snapshot (t/slot ~ truth).

## Ranking (real/d per rotation-validated competitor)

1. Affine (120)  ~4.35 TAO/d/comp  burn 0.92  immunity 16.7h  regs7d 119  -- best ratio; thin BECAUSE hard
2. Targon (4)    ~2.60             burn 0.00  immunity 25.1h  regs7d 219  -- free entry, highest churn
3. Chutes (64)   ~1.88             burn 0.00  immunity 16.7h  regs7d   6  -- most bankable, GPU-heavy
   AVOID: Minos(107)/Albedo(97) = king-of-the-hill; Verathos(96) = crowded (183 earners).

## Exit-liquidity flag
All seven have spot/d >= 2.1x real/d (Targon 6.9x, Chutes 6.8x, lium.io 6.5x the widest):
alpha is marked above the TAO actually flowing in, so exit liquidity — not emission —
is the binding constraint. real/d is the honest income figure; spot/d is inflated.

## Caveats
- real/d assumes the standard 18/41/41 owner/miner/validator split; custom cuts / v11 mechid will be off.
- Thin != easy: Affine is thin because 119 register and only ~8 earn. Verify you can produce the commodity.
- Shelf life is days; emission and competition both move.

## Run notes
- bittensor 11.0.0. Fixed one bug: fetch_history used `int(sub.block)`, but Subtensor.block
  is a METHOD in 11.0.0 (not a property) — int() on it raises TypeError. Now calls it.
- Archive node ran ~10 min/subnet under sustained load; full Step 2 pass ~70 min, no errors.
- CONFIG left at Step 2 values: HISTORY_DAYS=7.0, HISTORY_STEP_TEMPOS=3, NETUIDS=[97,120,64,4,107,51,96].
- subnets.{json,csv} = Step 2 output; subnets_step1.{json,csv} = Step 1 snapshot.

## Competition-only competitor overview (2nd pass, coarse 23-sample history)

Compute/serving markets excluded (Chutes 64, lium.io 51, Targon 4, Verathos 96, Gradients 56, Vidaio 85, MVTRX 79, iota 9, ...).

| net | name     | competes on               | TAO/d | paid | union/7d | rotation | genuine competitors            |
|----:|----------|---------------------------|------:|-----:|---------:|---------:|--------------------------------|
|  82 | Compelle | data/AI tasks             | 29.1 |   1  |    1     |  1.00    | ~1  single incumbent (monopoly)|
|  68 | NOVA     | pharma molecule discovery | 24.4 |   2  |    2     |  1.00    | ~2  thin, exotic work          |
|  38 | ChronoLLM| uncertain                 | 32.3 |   1  |    3     |  3.00    | ~3  (only 5 samples, low conf) |
| 120 | Affine   | RL / reasoning            | 84.9 |   5  |    8     |  1.60    | ~8  thin BECAUSE hard          |
|  44 | Score    | football prediction       | 40.3 |  10  |   26     |  2.37    | ~26 rotating (field ~246)      |
|  34 | BitMind  | deepfake detection        | 14.1 |  31  |   33     |  1.23    | ~33 moderate, stable           |
|   8 | Vanta    | proprietary trading       | 31.7 |  35  |   41     |  1.09    | ~41 moderate, stable           |
| 107 | Minos    | genomic variant calling   | 134.0|  20  |   72     |  3.61    | ~72-82 KotH (top1 90%)         |
| 114 | SOMA     | MCP servers               | 37.0 | 103  |  107     |  1.26    | ~107 crowded                   |
|  15 | ORO      | unverified                | 61.4 | 121  |  234     |  2.09    | ~234 crowded + rotating        |
|  97 | Albedo   | unverified                | 95.3 |   5  |   16     |  3.20    | ~254 KotH trap (looks empty)   |
|  67 | Harnyx   | deep-research agents      | 37.2 | 116  |  242     |  1.74    | ~242 most crowded              |

Thinnest genuine competitions with real inflow: Affine (~8), NOVA (~2, exotic), Compelle (~1, monopoly).
Purpose unverified: ORO (15), Albedo (97). ChronoLLM (38) history low-confidence (5 samples).

# ===== RE-RUN: block 8,721,365 (+9.0 days after first run) =====

Elapsed since first snapshot: 64,774 blocks = 9.0 days. Fresh 7d window barely
overlaps the original, so this is a near-independent measurement.

## Headline changes

| net | name      | TAO/d then->now | paid then->now | rotation then->now | verdict change              |
|----:|-----------|-----------------|----------------|--------------------|-----------------------------|
| 120 | Affine    |  84.9 -> 83.4   |    5 ->   5    |  1.60 -> 1.40      | STABLE + proven contestable |
|  97 | Albedo    |  95.3 -> 93.7   |    5 ->   5    |  3.20 -> 2.28      | same 5x20% split as Affine  |
| 107 | Minos     | 134.0 ->141.7   |   20 ->  20    |  3.61 -> (n/a)     | unchanged KotH (top1 89%)   |
|  38 | ChronoLLM |  32.3 -> 24.6   |    1 ->  10    |  3.00 -> 2.00      | OPENED UP (1 -> 10 winners) |
| 114 | SOMA      |  37.0 -> 28.4   |  103 ->   3    |  1.26 -> 1.00      | COLLAPSED to 3-winner wall  |
|  68 | NOVA      |  24.4 -> 21.2   |    2 ->   2    |  1.00 -> 3.00      | 88d incumbent GONE; reset   |
|  82 | Compelle  |  29.1 ->  8.1   |    1 ->   1    |  1.00 -> (n/a)     | inflow -72%, still WTA      |
|   8 | Vanta     |  31.7 ->  0.0   |   35 ->  36    |  1.09 -> (n/a)     | DEAD - zero TAO inflow      |
|  53 | engy      |   0.0 -> 30.3   |   -- ->  45    |   --  -> 3.33      | NEW (compute/serving mkt)   |
| 118 | Ditto     |   0.0 -> 22.9   |   -- ->   5    |   --  -> 5.40      | NEW - worst KotH seen       |
|   9 | iota      |  10.2 -> 33.7   |    2 ->   2    |   --  -> 1.38      | thin, lowest churn (5/wk)   |

## Affine (120): slot turnover proves contestability
Then earners: uid 5(13.7d) 96(4.9d) 145(9.6d) 178(17.1d) 210(12.7d)
Now  earners: uid 96(13.2d) 145(17.9d) 191(3.5d) 195(10.8d) 201(6.2d)
=> 3 of 5 slots changed hands in 9 days; uid 96/145 held. Still exact 20% x5
split (incentive 0.2 each). burn 1.02 -> 0.85 TAO. 111 joined last 7d.
This is the only candidate where breaking in is DEMONSTRATED, repeatedly.

## Corrections to the earlier report
- Albedo (97) is NOT a different animal from Affine: identical 5 x 20% even
  split. It just rotates ~2x faster (one earner 0.4d old), so slots are harder
  to HOLD. Earlier "KotH trap" framing was imprecise.
- NOVA (68): the 88-day entrenched incumbent no longer exists. All 59 miners
  registered within 7d; both earners 0.8d old. "Hardest wall" verdict is void -
  replaced by instability, not by an opening.
- Vanta (8) had TAO inflow cut to zero; its alpha income is now unbacked.

## Ranking (unchanged at #1)
1. Affine (120)  - contestable 5-slot even split, stable inflow, proven entry
2. ChronoLLM (38)- newly opened (1->10 winners, smooth decay), only 2 joins/wk,
                   BUT 168h immunity lock-up + 0.74 TAO burn
3. Albedo (97)   - same mechanism as Affine, faster turnover = harder to hold
AVOID: Ditto(118) rot 5.40; engy(53) compute market; Vanta(8) dead;
       Compelle(82) -72% inflow; SOMA(114) 245 miners scoring zero; Minos(107) KotH.

# ===== BROAD SWEEP: all subnets with >=5 TAO/d inflow =====

Structural scan (incentive shape + coldkey independence + ages + churn) on 12
previously unexamined subnets; rotation pass on 6 more. Coverage now ~34 of the
subnets that carry real TAO inflow.

## EV per strong miner = (miners' realizable TAO/day) / (distinct weekly earners)

| net | name      | real/d | earners | EV/miner  | burn | immunity | joins/7d |
|----:|-----------|-------:|--------:|----------:|-----:|---------:|---------:|
| 120 | Affine    |  34.22 |       7 | 4.89 TAO  | 0.84 |   16.7 h |      111 |
|   9 | iota      |  13.80 |       3 | 4.60 TAO  | 0.00 |   16.7 h |        7 |
| 107 | Minos     |  58.20 |      12 | 4.36 TAO  | 1.08 |   48.0 h |       29 |
| 114 | SOMA      |  11.98 |       3 | 3.99 TAO  | 0.33 |   16.7 h |      245 |
|  97 | Albedo    |  38.61 |      11 | 3.51 TAO  | 0.37 |   16.7 h |       98 |
|  17 | 404-GEN   |   4.42 |       3 | 1.47 TAO  | 0.00 |   16.7 h |        1 |
|  68 | NOVA      |   8.71 |       6 | 1.45 TAO  | 0.14 |   16.7 h |       62 |
|  24 | Quasar    |   4.64 |       4 | 1.16 TAO  | 0.00 |   36.0 h |        5 |
|  49 | Nepher    |   6.02 |       8 | 0.74 TAO  | 0.00 |   16.7 h |       14 |
|  38 | ChronoLLM |  10.08 |      20 | 0.50 TAO  | 0.74 |  168.0 h |        4 |
|   3 | sn3       |  10.95 |      24 | 0.46 TAO  | 0.02 |   33.3 h |      254 |
| 124 | Swarm     |   5.33 |      16 | 0.33 TAO  | 0.50 |   16.7 h |       21 |
|  53 | engy      |  12.63 |      55 | 0.23 TAO  | 0.00 |    0.0 h |      185 |
| 118 | Ditto     |   9.39 |      27 | 0.23 TAO  | 0.00 |    1.0 h |      172 |
|   1 | Apex      |   3.77 |      20 | 0.19 TAO  | 0.00 |   24.0 h |       54 |

KEY RESULT: EV converges to ~3.5-4.9 TAO/day for the top 5 despite wildly
different payout structures (even split / rotating jackpot / 3-way). Different
mechanisms, same expected value -> the market is pricing skill efficiently.
Structure determines VARIANCE and REQUIRED SKILL, not expected return.

## New structural findings
- sn9  iota: only 3 earners, 7 joins/wk, zero burn -- BUT requires A100-class
  80GB VRAM. Hardware capital wall, not a skill wall. Collaborative pretraining
  (contribution-scored), not a contest. One newcomer did enter (4.9d old).
- sn48 Quantum Compute: 6 "winners" but ALL SHARE ONE COLDKEY, ages 167-271d,
  1 join/wk. Fully captured by a single operator.
- sn17 404-GEN: 1 winner, 62d old, 0-1 joins/wk. Captured / abandoned.
- sn23 Trishool: 3 winners at exactly 33.3%, ages 34/175/182d. Frozen oligopoly.
- sn24 Quasar: rotation EXACTLY 1.00, 4 winners aged 24-36d, 5 joins/wk.
  Nobody has broken in for weeks -- stable oligopoly, low pay (1.16 TAO/d).
- sn3 "deprecated": mimics Affine's 5x20% split but rotation 4.84 with 254
  joins/wk. Churn lottery wearing an even-split costume. Avoid.
- sn49 Nepher: robotics policy tournament, explicit winner-take-all; champion
  seat rotated across 8 UIDs in 7d -> EV collapses to 0.74 TAO/d.

Affine (120) remains #1 on EV, and is the only top-EV option whose barrier is
skill you can build rather than hardware you must buy or a seat nobody vacates.
