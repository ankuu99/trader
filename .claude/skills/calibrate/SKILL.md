---
description: Calibrate one or more stocks in two stages — first find the right timeframe regime (15minute global config vs the standard 4hour/day template blocks), then the right params within the winner (threshold sweep for 4hour/day; threshold × forward_label grid for 15minute). Emits a paste-ready per_stock_params block for aggregated winners. --no-compare re-calibrates threshold inside a stock's already-settled regime.
argument-hint: <SYMBOL> [SYMBOL ...] [--from YYYY-MM-DD] [--thresholds 0.80 0.85 ...] [--no-compare] [--cache-only]
---

Calibrate stocks with regime selection first, params second. Multiple symbols may
be passed at once — each is reported independently.

## Step 1 — Run the calibration

```bash
python scripts/calibrate_stock.py $ARGUMENTS 2>/dev/null
```

The script fetches missing 15m history from Kite by default (deep enough to cover
the day-template warm-up — ~2 years before `--from`) and auto-refreshes an expired
token via `kite_totp_refresh.py` — a fresh pull is always fine, never ask
permission for it. Pass `--cache-only` only when re-running symbols already
fetched this session. Use a generous Bash timeout (10+ min): the default flow runs
1 + 12 + grid backtests per symbol.

Two modes:
- **Default (full flow)** — Stage 1 backtests the stock as: 15minute with the
  global config, 4hour with the standard template block, day with the standard
  template block (threshold swept over 0.80–0.92 for the aggregated legs). The
  best-P&L regime wins. Stage 2: if an aggregated TF won, the threshold sweep
  already IS the param calibration and the JSON includes `recommended_override` —
  the full standard block with the winning threshold; if 15minute won, the legacy
  threshold × forward_label grid runs.
- **`--no-compare`** — skips regime selection; sweeps threshold inside the stock's
  CURRENT merged config (including its `timeframe`). Use for quick re-calibration
  of stocks whose regime is already settled.

## Step 2 — Parse the JSON

Single symbol → flat object; multiple → `stocks: {sym: {...}}`. Fields:
- `mode` — `full` or `current_regime`
- `regime` (full mode) — winning TF; `legs` — per-TF results: `legs["15minute"]`
  is a single run of the global config, `legs["4hour"]`/`legs["day"]` have
  `results` (threshold sweep) and `best`. If the stock already has a per-stock
  override, `legs["current"]` races the hand-tuned block too — `regime` can be
  `"current"`, meaning KEEP the existing block as-is (a customised block can
  legitimately beat the standard template; fine-tune it with `--no-compare`)
- `recommended_override` (full mode, aggregated winner) — nested config block,
  paste-ready for `per_stock_params.<SYM>.lr_extrema`
- `baseline` / `results` / `best` — param-grid output (15minute winner or
  `--no-compare` mode); `delta` is vs the baseline config
- `current_override` — what's in `per_stock_params` today (if anything)
- `coverage_warning` — the 15m cache doesn't reach far enough BEFORE `--from` to
  cover warm-up. With auto-fetch this only happens when Kite itself lacks 15m
  depth for the symbol (recent listings) or `--cache-only` was passed. Report it
  prominently — results are warm-up-starved and trade counts understated.

## Step 3 — Display results

Per stock, show the regime comparison first, then the param calibration:

```
=== Calibration: <SYMBOL> ===
Regime:   15minute (global)   P&L=₹X    trades=N   WR=X%
          4hour    best 0.85  P&L=₹Y    trades=N   WR=Y%
          day      best 0.82  P&L=₹Z    trades=N   WR=Z%   ← WINNER

day threshold sweep:
  th      trades    P&L        WR
  0.82      14   ₹12,196     57%
  ...
```

## Step 4 — Recommend

- Prefer the winning regime unless it wins on a knife-edge single threshold —
  check the neighbours in the sweep; a flat profitable region beats a lone spike.
- If the aggregated legs only marginally beat 15minute (< ~20% better P&L), say
  so — 15minute needs no per-stock block and trades more often (more signal).
- Low trade counts are structural on day TF; compare thresholds against each
  other rather than dismissing the stock, but flag < 5 trades as unreliable.
- If every leg is negative, recommend not adding the stock (or removal).
- 15minute winner: apply the "more selective" rule — prefer higher threshold or
  forward_label with meaningful min_return_pct; flag sub-0.90 thresholds as a
  portfolio-crowding risk (this concern does NOT apply to 4hour/day).

For an aggregated winner, render `recommended_override` as the standard yaml
block (same shape as the existing ACMESOLAR/SCHAEFFLER blocks — comments
optional):

```yaml
NSE:SYMBOL:
  lr_extrema:
    timeframe: day
    warmup_bars: 100
    lookback_bars: 400
    threshold: 0.85          # calibrated
    retrain_every: 1         # 2 for 4hour
    extrema_order: 5
    exits:
      hold_bars: 40
      sell_min_pct: 7.0
      hard_stop: {stop_pct: 20}
      trailing: {profit_pct: 10, trail_pct: 4, force_close_time: null}
      pattern_top: {sell_threshold: 0.85, min_hold_before_exit: 2}
      stale: {check_bars: 5, min_gain_pct: 0.5}
      stale_2: {check_bars: 15, min_gain_pct: -2.0}
```

## Step 5 — Ask to apply

Ask the user: "Apply this to config.yaml?"

If yes:
1. Read `config/config.yaml`
2. Aggregated winner → write the full `recommended_override` block under
   `per_stock_params` (replace any existing block for the symbol), formatted like
   the existing hand-written blocks (expanded yaml with comments, not flow style)
3. 15minute winner → update or add the threshold/forward_label override as before;
   if the stock previously had an aggregated block, REMOVE it (regime changed)
4. `--no-compare` mode → update ONLY the `threshold:` key inside the existing block
5. Confirm what changed

If the recommendation is "don't add / remove", ask about the watchlist instead.
