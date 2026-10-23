---
description: Replay LRExtremaStrategy on a stock to see per-candle P(local-min) and P(local-max) probabilities, identify where entry gates and sell gates fired, and diagnose why exits did or didn't trigger.
argument-hint: NSE:SYMBOL [--show-from YYYY-MM-DD] [--from YYYY-MM-DD]
---

Replay the LRExtremaStrategy on a single stock and analyse the model's probability output candle-by-candle.

## Step 1 — Run the replay

```bash
python scripts/replay_strategy.py $ARGUMENTS 2>/dev/null
```

The table columns:
- `Timestamp` — candle close time
- `Close` — closing price
- `Change%` — bar-over-bar % change
- `P(min)` — model's probability that this candle is a local minimum (entry signal when ≥ threshold)
- `P(max)` — model's probability that this candle is a local maximum (pattern-top exit when ≥ sell_threshold)
- `Notes` — flags when ENTRY_GATE or SELL_GATE thresholds are crossed

Default params (from config or per_stock_params override):
- `threshold` (default 0.90) — P(min) must exceed this to fire a BUY entry
- `sell_threshold` (default 0.85) — P(max) must exceed this to fire a pattern-top exit
- `sell_min_pct` (default 3.0%) — minimum gain required before pattern-top exit can fire
- `profit_pct` (default 10%) — gain required before trailing stop arms

## Step 2 — Identify key events

Scan the table for:
1. **Entry candles** — rows with `ENTRY_GATE` note (P(min) ≥ threshold). The live bot entered on the first one where `is_flat()` was true.
2. **Sell gate crossings** — rows with `SELL_GATE` note (P(max) ≥ sell_threshold). These are the only candles where a pattern-top exit *could* have fired.
3. **The price peak** — the candle with the highest close after entry. Check what P(max) was there — often it's surprisingly low.

## Step 3 — Diagnose missed exits

If P(max) was low at the actual price peak, the model didn't recognise it as a top. The features driving P(max) are:
- **Return slopes** (3, 5, 10, 20-bar % return slopes) — a local maximum typically shows a flattening or reversal in these slopes
- **norm_price** — `(close - low) / (high - low)`: at a top, price often closes near the high (norm_price → 1), which the model associates with *continuation*, not reversal
- **volume_ratio** — volume spike at a top is a bearish signal; absence of volume spike at a gradual rally peak means P(max) stays low

Common reasons P(max) stays low at a price peak:
- **Gradual grind-up**: slopes are still positive/flat, not reversing — model doesn't see the reversal pattern
- **No volume spike**: quiet rally with average volume — model trained on high-volume tops doesn't fire
- **Bar closed near high**: norm_price high → model sees it as a continuation candle, not a top
- **Gap-up open at start of day**: the model sees a sharp 1-bar move as a top (P(max) spikes at open), but then price continues — these are false SELL_GATE crossings

## Step 4 — Recommend parameter changes

Based on the analysis:

| Observation | Suggested fix |
|-------------|---------------|
| P(max) never reaches sell_threshold even at peak | Lower `sell_threshold` (e.g. 0.80) |
| SELL_GATE fires at gain < sell_min_pct (exit blocked by floor) | Lower `sell_min_pct` (e.g. 2.0%) |
| Trailing never arms because profit_pct too high | Lower `profit_pct` (e.g. 4–5%) |
| P(max) spikes on gap-up opens (false signals) | Raise `sell_threshold` or raise `sell_min_pct` |
| Position held too long, exits on hold_bars timeout | Lower `hold_bars` or lower `profit_pct` |

Show the suggested override as a yaml snippet and ask whether to apply it to config.yaml.

## Step 5 — Ask before acting

Do NOT modify config.yaml without explicit confirmation.

If the user confirms a parameter change, update `per_stock_params` in `config/config.yaml` for the symbol.
