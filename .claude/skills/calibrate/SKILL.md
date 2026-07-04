---
description: Calibrate strategy params for one or more watchlist stocks — TF-aware (15minute stocks get threshold × forward_label; 4hour/day stocks get a threshold-only sweep in their own aggregated regime). Shows ranked grid results vs the stock's current config, and optionally applies the best threshold to per_stock_params in config.yaml.
argument-hint: <SYMBOL> [SYMBOL ...] [--from YYYY-MM-DD] [--thresholds 0.80 0.85 ...]
---

Calibrate strategy parameters via grid search. Works per-timeframe: each stock is
backtested with its CURRENT merged config (global + per_stock_params, including
`timeframe`) as the base, so 4hour/day stocks are calibrated on aggregated bars
with all their standard overrides intact. Multiple symbols may be passed at once.

## Step 1 — Run the grid

```bash
python scripts/calibrate_stock.py $ARGUMENTS 2>/dev/null
```

Parse the JSON output. Single symbol → flat object; multiple symbols → `stocks: {sym: {...}}`.
Each stock's object contains:
- `timeframe` — the stock's strategy TF (15minute / 4hour / day)
- `current_threshold` — threshold the stock runs today
- `baseline` — performance of the stock's current merged config (NOT the global defaults)
- `current_override` — the raw `per_stock_params` block (if any)
- `results` — top 10 combos ranked by P&L: `fl`, `min_return_pct`, `threshold`, `pnl`, `trades`, `win_rate`, `delta` (vs baseline). For 4hour/day stocks `fl` is always false — only `threshold` varies.
- `best` — the top-ranked combo
- `coverage_warning` — present if the 15m cache doesn't reach far enough BEFORE `--from` to cover the aggregated-TF warm-up (warmup_bars + lookback_bars). If present, results are warm-up-starved: report the warning prominently and treat trade counts as understated. Fixing it requires fetching older 15m history (or, on a fresh symbol, deleting its 15m rows and re-fetching).

## Step 2 — Display results

Print a clean table per stock (omit the FL/mr columns for 4hour/day stocks):

```
=== Calibration: <SYMBOL> [day] ===
Current config: threshold=0.85  →  P&L=₹X  trades=N  WR=X%

Rank    th    trades    P&L        WR      vs current
----  ----  ------  ---------  ------  -----------
  1   0.82     14   ₹12,196     57%     +₹2,609
  ...
```

## Step 3 — Recommend

- **15minute stocks** — apply the "more selective" rule: prefer overrides more selective than global defaults (higher threshold OR forward_label with meaningful min_return_pct); flag a sub-0.90 threshold as a portfolio-crowding risk.
- **4hour/day stocks** — lower thresholds (0.80–0.85) are acceptable and expected: aggregated bars fire far less often, so crowding is not a concern. Recommend the highest-P&L threshold that isn't a knife-edge — check the neighbours in the results; if 0.85 wins but 0.82 and 0.88 are both sharply worse, prefer the flatter region over the single spike.
- Results with < 5 trades should be flagged as statistically unreliable even if P&L looks good; for day-TF stocks low counts are structural, so compare thresholds against each other rather than dismissing the whole stock.
- If every combo is negative, say so clearly and recommend removal from the watchlist.

Show the recommended change as a yaml snippet (for 4hour/day stocks this is just the `threshold:` line inside the existing per-stock block — never regenerate the whole block):

```yaml
NSE:SYMBOL:
  lr_extrema:
    threshold: X.XX
```

## Step 4 — Ask to apply

Ask the user: "Apply this to config.yaml?"

If yes:
1. Read `config/config.yaml`
2. For a 4hour/day stock, update ONLY the `threshold` key inside its existing `per_stock_params` block (the rest of the block is the standard TF override — leave it untouched)
3. For a 15minute stock, update or add the `per_stock_params` entry as before
4. Confirm what changed

If the recommendation is removal (all combos negative), ask: "Remove this stock from the watchlist instead?"
