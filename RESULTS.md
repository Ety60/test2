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
