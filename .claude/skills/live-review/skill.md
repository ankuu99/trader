---
description: Live trade performance review — pulls the EC2 DB, compares real fills against backtest expectations per stock, and recommends removals or recalibrations based on actual live behaviour.
argument-hint: [--skip-refresh] [--days N]
---

Analyse live (EC2) trade performance against backtest expectations and recommend actions.

## Step 1 — Fetch live vs backtest data

Run the following command. Pass through any arguments the user provided (e.g. `--skip-refresh`, `--days 60`):

```bash
python scripts/live_performance.py $ARGUMENTS 2>/dev/null
```

Parse the JSON output. It contains:
- `portfolio` — aggregate live P&L, trades, win rate
- `stocks` — per-stock dict with:
  - `live`         — actual live metrics: pnl, trades, win_rate, avg_win, avg_loss
  - `backtest`     — backtest metrics over the same date window
  - `expected_pnl` — backtest avg P&L/trade × live trade count (what we should have made)
  - `pnl_gap`      — live.pnl − expected_pnl (negative = underperforming)
  - `wr_gap`       — backtest.win_rate − live.win_rate (positive = live win rate is lower)
  - `flag`         — GREEN / AMBER / RED / SPARSE

## Step 2 — Classify each stock

| Flag | Meaning | Default action |
|------|---------|----------------|
| **RED** | Live P&L < -₹3,000 OR (wr_gap > 20pp AND live P&L negative) | REMOVE or urgent recalibrate |
| **AMBER** | wr_gap > 12pp OR live P&L < -₹500 | WATCH / recalibrate |
| **GREEN** | Performing in line with or better than backtest | KEEP |
| **SPARSE** | Fewer than 5 live trades — insufficient data | Note only, no action |

Upgrade a stock from GREEN → AMBER if:
- News shows a material negative development (earnings warning, SEBI action, sector headwind)
- The live avg_loss is more than 2× the backtest avg_loss (stop-outs larger than expected)

## Step 3 — Display results

Print a clean table showing every stock:

```
=== Live Performance Review ===
Period: YYYY-MM-DD → YYYY-MM-DD   |   Portfolio: P&L=₹X  trades=N  WR=X%

Stock         Live P&L  Live WR  BT WR   WR gap  Expected P&L   Gap      Flag
-----------  ---------  -------  ------  ------  ------------  -------  ------
NSE:CUPID      ₹4,231    64.3%   50.0%   -14.3   ₹3,100       +₹1,131  GREEN
NSE:RVNL      -₹1,820    20.0%   47.1%   +27.1   ₹1,050       -₹2,870  RED
...
```

Then print a summary:
```
RED   (remove/recalibrate): [list]
AMBER (watch/recalibrate):  [list]
GREEN (keep):               [list]
SPARSE (< 5 trades):        [list]
```

## Step 4 — Recommend actions

For each RED stock:
- If backtest P&L is also weak (< ₹5,000 full period): recommend REMOVE
- If backtest P&L is strong but live diverges: recommend urgent recalibrate — live regime has shifted

For each AMBER stock:
- If wr_gap > 15pp: recommend recalibrate
- If wr_gap 12–15pp with positive live P&L: recommend WATCH for one more cycle

For SPARSE stocks:
- Note the trade count and say "insufficient data — check again in 2–4 weeks"

## Step 5 — Ask before acting

Ask the user:
1. "Remove RED stocks? [list]" — if confirmed, remove from config.yaml watchlist
2. "Run calibration for RED/AMBER stocks? [list]" — if confirmed, invoke the calibrate skill for each

Do NOT modify config.yaml without explicit confirmation.

If the user confirms calibration, invoke the calibrate skill for each stock in sequence:

```
Skill("calibrate", "NSE:SYMBOL")
```

Show each calibration result and ask whether to apply before moving to the next stock.

## Notes

- A stock can look RED in live mode simply because it has had a bad streak — cross-check against the backtest window to distinguish bad luck from structural breakdown
- SPARSE results are normal for recently-added stocks or low-frequency signals; do not act on them
- `pnl_gap` is the most actionable metric: a large negative gap means the strategy is generating the right number of trades but losing where the backtest predicts wins
- avg_loss significantly larger than backtest avg_loss suggests real slippage or a gap-down risk that the backtest underestimates
