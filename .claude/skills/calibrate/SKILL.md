---
description: Calibrate threshold × forward_label params for a single watchlist stock. Shows ranked grid results vs baseline, compares to current override, and optionally applies the best config to per_stock_params in config.yaml.
argument-hint: <SYMBOL> [--from YYYY-MM-DD]
---

Calibrate a single stock's strategy parameters via grid search.

## Step 1 — Run the grid

```bash
python scripts/calibrate_stock.py $ARGUMENTS 2>/dev/null
```

Parse the JSON output. It contains:
- `baseline` — performance with global params and no override
- `current_override` — what's currently in `per_stock_params` for this stock (if anything)
- `results` — top 10 combos ranked by P&L, each with: `fl` (forward_label enabled), `min_return_pct`, `threshold`, `pnl`, `trades`, `win_rate`, `delta`
- `best` — the top-ranked combo

## Step 2 — Display results

Print a clean table:

```
=== Calibration: <SYMBOL> ===
Baseline (global params): P&L=₹X  trades=N  WR=X%
Current override: <show yaml snippet or "none">

Rank  FL    mr    th    trades    P&L        WR      vs baseline
----  ----  ----  ----  ------  ---------  ------  -----------
  1   True  2.0  0.92     85   ₹2,196     40.0%     +₹2,609
  2   False  —   0.92     87   ₹2,053     36.8%     +₹2,467
  ...
```

## Step 3 — Recommend

Apply the "more selective" rule:
- Only recommend overrides that are **more selective** than global defaults (higher threshold OR forward_label enabled with meaningful min_return_pct)
- Flag if the best combo is less selective (lower threshold than 0.90) — note it improves in isolation but may crowd out other stocks in the portfolio
- If the best result is still negative (no combo produces positive P&L), say so clearly and recommend removal from watchlist

Show the recommended override as a yaml snippet:
```yaml
NSE:SYMBOL:
  lr_extrema:
    threshold: X.XX
    forward_label:
      enabled: true
      min_return_pct: X.X
```

## Step 4 — Ask to apply

Ask the user: "Apply this override to config.yaml?" 

If yes:
1. Read `config/config.yaml`
2. Update or add the `per_stock_params` entry for this symbol
3. If the symbol already has an override, replace it
4. Confirm what changed

If the recommendation is removal (all combos negative), ask: "Remove this stock from the watchlist instead?"

## Notes on trade count
- Results with < 5 trades over 3 years should be flagged as statistically unreliable even if P&L looks good
- Prefer the highest-P&L combo that has >= 10 trades when multiple good options exist
