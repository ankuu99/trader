# Trader — Project Reference for Claude Agents

## What this is
An automated equity trading system for Indian markets (NSE) using Zerodha/Kite. Supports paper and live modes. Strategies emit signals; a risk layer sizes and places orders; a live WebSocket feed assembles candles.

The system is **long-only, delivery (CNC) only**, targeting multi-day swing trades on NSE-listed equities. It is not an intraday system.

---

## Project tracking & dev workflow (adopted 2026-10-17)

**Anything discussed must end up in a durable file in the same session** — a chat mention is not
documentation. Commit and push after each finished chunk of work (not every message). Index: `README.md`.

- **`DECISIONS.md`** — dated ADR-lite log, one row per decision, newest at the bottom. Superseded rows are
  struck through (`~~…~~`) with a pointer to the replacement, never deleted.
- **`ISSUES/ISS-NN-<slug>/`** — `SUMMARY.md` (one-liner, area, nuanced status, fix commits) · `DETAIL.md`
  (report verbatim + dated addenda, never deleted) · empty `FIXED` | `PENDING` marker (`ls ISSUES/*/PENDING`
  = open list). `ISSUES.md` = slim index. A reported problem gets its folder **before** any fix; on fix,
  update SUMMARY status, rename the marker and the index row in the same commit.
- **`TODO/TD-NNN-<slug>/`** — same mechanism (`DONE` | `PENDING`), `TODO.md` = index grouped by section.
  Discovered constraints / external requirements get the next TD number immediately; every "out of scope"
  bullet in a guide gets its own TD and the guide cites it. (Replaced the old `todo.md` — same path on
  macOS's case-insensitive FS.)
- IDs are permanent, never reused. Statuses carry nuance (`FIXED pending field validation (abc123)`,
  `DONE 2026-08-25 — <why>`).
- **Spec-first builds — `to_develop/`** (loop + template in `to_develop/README.md`): the main session writes
  `YYYY-MM-DD_TAG_slug.md` (TAG = ISS-NN | TD-NNN | DOC-NN | DEC) opening with a `## Source` block quoting the
  tracker entry verbatim → the `trader-implementer` subagent (`.claude/agents/`, pinned model) builds exactly
  that → the main session validates (full pytest + diff vs the acceptance checklist; never trust the report)
  → append the Completion record and `git mv` the guide to `to_develop/completed/` (the move is the sign-off),
  flipping the ISS/TD status in the same commit. On fail: dated addendum in the guide, repeat. The guide
  must carry every judgment call — the implementer only executes.
- **`to_develop/WHATS_NEXT.md`** — suggested pickup order, refreshed near the end of every chunk (< 100 lines;
  a summary, not a second TODO). The owner decides what starts.
- **Session discipline** — track the owner's requests in a session task list and close items as they finish.
  When the owner reports a problem: assess first, fix only on their go (straightforward, already-documented
  bugs are pre-approved). Run the full test suite before every commit. Trackers lag the code — grep the source
  before writing a guide from a TD item. Repeated procedures become skills in `.claude/skills/`.

---

## Running the system

```bash
python main.py                        # paper/live trading (uses config/config.yaml)
python main.py --config <path>        # alternate config
python scripts/backtest.py --from 2025-01-01 [--to 2025-12-31] [--timeframe 5minute|15minute|...]
python scripts/calibrate.py --from 2025-01-01 [--mode grid|random] [--iterations 50] [--workers N] [--params profit_pct stop_pct ...]
python scripts/backtest_rolling.py --from 2024-01-01 --to 2025-12-31 [--window 6] [--step 3] [--symbols NSE:X] [--timeframe ...]
python scripts/screen.py --from 2025-01-01 [--min-trades 2] [--output results.csv] [--timeframe ...]
python scripts/kite_auth_server.py    # refresh Kite access token (run on EC2, open URL in any browser)
```

---

## Scale-in (geometric add-ons)

Portfolio-level feature (validated by the 2020–2026 counterfactual, 2026-07-07): while in a
position, an in-position ENTRY signal that would fill ≥`min_spacing_days` after the last
investment buys an add-on lot sized `fraction_pct`% of the **previous** lot's notional
(geometric decay), up to `max_addons` tiers. All exits sell the entire blended position.

- **Signal source** — `lr_extrema` already emits stateless in-position ENTRY signals;
  `RiskManager.validate()` routes them to `_validate_addon()` when `scale_in.enabled`
  (otherwise rejects `already_in_position` as before). Add-ons bypass `max_open_positions`
  (not a new position) but honour halt/pause/pending checks. Reject reasons:
  `addon_limit_reached`, `addon_spacing`, `addon_budget_exhausted`, `addon_qty_zero`,
  `addon_no_state`.
- **Budget pool on top of base capital** — add-on cost basis is tracked in
  `RiskManager._scale_in_deployed` (capped at `budget_pct`% × total capital, including
  in-flight add-on pendings) and never touches `_capital_deployed`, so base entry sizing is
  unaffected. The cap is enforced at order approval on the signal price — next-open fill
  gaps can overshoot it slightly (observed ~9% peak in the 2020–2026 validation run). In
  live mode the account must actually hold the extra cash.
  **Live funding (2026-10-17):** the pool is never reserved out of the base —
  `main.py::_apply_effective_capital` sets `config.set_scale_in_budget(scale_in_pool(equity, base, cap))`
  = min(budget_pct × config-file capital, Kite equity − (config-file capital + realised cumulative P&L)), floor 0
  (cum P&L 0: ₹6.3L equity on a ₹6L base → ₹30k pool; ≥ ₹6.6L → ₹60k; ≤ ₹6L → no add-ons). **Profits grow the base
  sleeve first** (ISS-04, `risk.manager.live_capital_split`): effective total_capital + cum P&L = min(base + cum P&L, equity) —
  Kite equity already contains realised P&L, so it is never added on top again. Equity = cash + base deployed + add-on
  deployed. Backtest/paper keep budget_pct × capital. Dashboard Capital card shows free/used/funded/cap
  and the equity-vs-base line. **ENABLED 2026-10-17** together with the loss re-entry block
  (`reviews/scalein_lossblock_2020_horizon_20261017.md`).
- **STALE ANCHOR IS PARENT-FROZEN (critical invariant)** — add-on fills carry
  `addon: True` through OrderManager dispatch; `lr_extrema.on_order_update` returns
  immediately for them, so `_entry_price`, `_held_bars`, `_peak_close`, `_trailing_active`
  never re-anchor to the blended entry. Re-anchoring would restart the stale runway on
  falling-knife positions — the one failure mode that turns the brake into an enabler.
  `pct_change` in the UI stays parent-anchored; unrealised P&L uses blended avg cost.
- **Engine** — positions carry a `lots` list (lots[0] = parent); every exit path emits one
  trade record per lot via `_consume_lots` (FIFO for partial scale-outs), with per-lot
  costs/MIS-CNC detection and the `addon_tier` key (0 = parent).
- **Persistence** — add-on lots live in the `open_positions.addon_lots` JSON column
  (`store.add_position_lot`; each lot keeps its original `notional`); parent entry_price/entry_time untouched. Partial scale-outs reduce the parent and every lot **proportionally** (`store.consume_position_lots`, whole shares by largest remainder, zero-qty lots kept) — the same as `RiskManager.reduce_position`, so the daily reboot never changes avg cost, pool usage, realised/cumulative P&L or loss-block arming (ISS-03, `tests/test_scaleout_reboot_parity.py`). Restart seeding:
  `risk.seed_position(parent)` + `risk.restore_parent_notional(open_positions.parent_notional)` + `risk.seed_scale_in(addon_lots)` — the parent's ORIGINAL ₹ notional is persisted at the parent fill so the first add-on after a scale-out + reboot is sized like the no-reboot path (TD-015; legacy rows = 0 → sized off the remainder).
- **calibrate.py / screen.py force `scale_in.enabled=false`** — per-stock param search and
  screening stay un-levered; validate scale-in via backtest.py / backtest_rolling.py.
- No GTT is ever placed for add-on lots.

---

## Per-stock aggregated timeframes (4hour / day)

A stock can run its strategy on `4hour` or `day` bars built in memory from 15m base
candles (`trader/data/aggregator.py::CandleAggregator`), while fills, intrabar SL/target,
tick exits and the UI stay on the 15m stream. Configure via
`per_stock_params.<sym>.lr_extrema.timeframe: day` — and override ALL TF-sensitive params
for that stock (startup logs a warning per missing one). Bar boundaries are FROZEN:
day = 09:15–15:15, 4hour = 09:15–13:15 + 13:15–15:15; the 15:15–15:30 tail is dropped.
Bars emit on their last member candle (~15:15 decision, same-day entry); the scheduler
flushes stragglers at 15:16 IST. Only 15m candles are persisted — never store aggregated
bars. `calibrate.py --strategy-timeframe day` calibrates at an aggregated TF. Full
rationale and decision log: `docs/Aggregated_Timeframes_Design.md`.

---

## Core data flow

```
LiveFeed (KiteTicker ticks)
  └─ assemble candles by timeframe
      └─ handle_candle() in main.py
          ├─ orders.on_candle()         → fills pending paper orders at open price
          └─ strategy.on_candle()       → returns Signal | None
              └─ risk.validate(signal)  → returns Order | None
                  └─ orders.place(order)
                      ├─ paper: queues in _pending_paper (fills next candle open)
                      └─ live:  kite.place_order() + optional GTT OCO

LiveFeed (KiteTicker on_order_update) [live mode only]
  └─ orders.on_kite_order_update()
      └─ _dispatch(record)
          └─ handle_order_update() in main.py
              ├─ BUY fill → risk.on_order_filled(), portfolio.on_order_filled()
              ├─ SELL fill → risk.close_position()
              ├─ telegram.notify_order_filled()
              └─ strategy.on_order_update()   → updates strategy position state + _entry_price
```

---

## Signal contract

Fields: the commented `Signal` dataclass in `trader/strategies/base.py`.

**EXIT signals** bypass RiskManager's position-conflict check. RiskManager returns a SELL Order using the quantity stored from the original ENTRY fill.

**`signal_type` flows through the Order and dispatched record** — `strategy.on_order_update()` reads it to distinguish entry fills (sets `_entry_price`) from exit fills (clears state).

---

## Adding a new strategy

1. Create `trader/strategies/<name>.py` — subclass `Strategy`, implement `name` property and `on_candle(candle) -> Signal | None`
2. Register in `trader/strategies/registry.py` — add to `build_strategies()`
3. Add config block under `strategies:` in `config/config.yaml`

Key rules:
- Strategies never import from `orders/` or `risk/`
- Use `self.is_flat()` to gate entries
- Set `self._entry_price = price_hint` at signal time to guard against re-entry while awaiting fill; override with real fill price in `on_order_update()`
- Pass `stop_loss_hint` and `target_price` in the ENTRY signal so RiskManager and the backtest engine use the strategy's own levels rather than config fallbacks
- Override `on_order_update()` if strategy needs to track fill state (e.g. `_entry_price`)
- For strategy-driven exits: emit `Signal(direction=BUY, signal_type=EXIT, ...)`

---

## RiskManager behaviour

- ENTRY signals: checks halt, max positions, duplicate instrument → sizes quantity
- EXIT signals: skips conflict check → returns SELL Order with stored quantity
- `_open_positions: dict[str, int]` — instrument → quantity
- `_position_values: dict[str, float]` — instrument → entry_price × qty (for capital tracking)
- `_cumulative_pnl: float` — lifetime P&L, never resets; persisted to SQLite `state` table in live mode so it survives restarts
- `capital_available` property — `total_capital + cumulative_pnl - capital_deployed - pending`; quantity is capped so portfolio never over-deploys. In live mode `total_capital` is capped at startup by Kite available cash (see Known design decisions)
- `seed_cumulative_pnl(pnl)` — called on startup in live mode to restore cumulative P&L from the `state` table
- `cumulative_pnl` property — read-only access to `_cumulative_pnl`
- `on_order_filled()` records deployed capital; `close_position()` frees it and adds to `_cumulative_pnl`
- `_last_reject_reason` — set at each rejection point (`daily_halt`, `max_positions`, `slow_tf_limit`, `already_in_position`, `pending_order_exists`, `sl_distance_zero`, `quantity_zero`, `reentry_cooldown`, `reentry_discount`, `loss_reentry_block`, plus the `addon_*` reasons); surfaced in UI signals table
- **Slow-TF slot cap** (`risk.max_slow_tf_positions`, default **null** = off): caps concurrent open+pending positions whose strategy timeframe is aggregated (`config.is_aggregated_tf`, memoised). Base-TF entries are never blocked by it; reject reason `slow_tf_limit`. Motivation: 4hour/day round-trips hold capital 2–3.5× longer per trade (2026-08-16 live forensics). **FALSIFIED as a P&L fix 2026-08-16** (A/B 2025-01→2026-08: baseline ₹294k/Calmar 3.09 → cap=6 ₹242k/2.29 → cap=4 ₹194k/2.19, DD not improved) — slow-TF trades are the portfolio's biggest winners; capping them redeploys capital into marginal 15m entries whose stale losses swamp the gain. Kept OFF as a defensive-only option; the funding fixes are ISS-04 (ledger double-count) and TD-001 (pre-order margin check). Fixed-engine re-run 2026-10-16: still negative (cap=6 −₹89k, cap=4 −₹172k) but half the old size
- **Same-day re-entry cooldown** (`risk.reentry_cooldown_enabled`, default **false**): after a position is FULLY closed, ENTRY signals for that instrument are rejected (`reentry_cooldown`) for the rest of the session. `_reentry_blocked: set[str]` is armed in `close_position()` **only when `exit_price` is truthy** — `post_market()` evicts stale positions with `close_position(inst, 0.0)` as bookkeeping, and arming on those would make correctness depend on eviction running before `reset_day()` in the same job. Cleared in `reset_day()`, which is the sole clock: no timestamps are stored, so live (`main.py` post-market) and backtest (engine day boundary) share one mechanism. Partial scale-outs never arm it — `reduce_position()` delegates to `close_position()` only when the remainder hits zero. EXIT signals are unaffected (they return before the check). **⚠ Re-run 2026-10-16 on the fixed engine** (pre-order-reject freeze, see Known design decisions): −₹4.3k vs baseline, Calmar 5.96→6.10 — the old −34% was the freeze artifact. `reviews/reject_freeze_rerun_20261016.md`
- **Same-day re-entry discount gate** (`risk.reentry_discount: {enabled, min_discount_pct, max_premium_pct}`, default **false**): after a full close, an ENTRY on that instrument the same session is rejected (`reentry_discount`) unless priced at least `min_discount_pct` BELOW the **blended** exit price of the round trip just closed. `_exit_today: dict[str, [proceeds, qty]]` accumulates every exit (partial scale-outs via `reduce_position` + the final `close_position`) since the last entry fill, so the reference is the true average price we got out at; it is cleared on the next non-add-on entry fill and in `reset_day()` (same shared clock as the cooldown). `exit_price=0` evictions never arm it. `max_premium_pct` (null = one-sided) re-opens the top of the band so a re-entry priced well ABOVE the exit is let through. **FALSIFIED 2026-08-26** (A/B 2025-01→2026-08, baseline 418t/₹303k/Calmar 3.12): ±0.1% → ₹272k, ±0.25% → ₹273k, ±0.5% → ₹258k, one-sided 1.5% → ₹127k/Calmar 1.39 — monotone in width, DD unimproved, and even the hair-thin band costs ₹31k of P&L to save ₹3.9k of charges. Blocking a re-entry amputates the downstream trade sequence; the loss is idle capital (util 61.8%→36.7%), not charges. Kept OFF as a defensive-only option — do not re-tune the width. See `reviews/reentry_discount_ab_20260826.md`. **⚠ Re-run 2026-10-16 on the fixed engine:** 1.5% one-sided +₹6.0k, ±0.25% +₹4.1k vs baseline — the falsification was the pre-order-reject freeze; re-open only with multi-window validation
- **Loss re-entry block** (`risk.loss_reentry_block: {enabled, sessions}`, default **false**): after a full close that realises a LOSS, ENTRY signals for that instrument are rejected (`loss_reentry_block`) until N sessions have elapsed — `_loss_reentry: dict[str, int]` counts down one per `reset_day()` (same shared clock as the cooldown); `seed_loss_reentry()` / `loss_reentry_state` exist for live restart seeding. **FALSIFIED as a standalone rule 2026-08-16** (engine-level −₹69k vs baseline over 2025-01→2026-08 — blocking one rebuy amputates the downstream trade sequence, same shape as the blanket cooldown); kept OFF as a defensive-only option. Winning exits and exit_price=0 evictions never arm it. **ENABLED 2026-10-17 (3 sessions) with scale-in** — 2020→2026 sweep: beats baseline 6/7 calendar years, full-period DD 42→36.8 %; 10 sessions = crash insurance (COVID DD 20 %) at −₹106k ex-2020. Live countdown persists across the daily reboot as `<inst>.loss_reentry_sessions` state keys (`Store.save_loss_reentry/load_loss_reentry`; saved after every full close and post-market `reset_day`, seeded at boot) — without it the block only covered the rest of the exit day. **⚠ Re-run 2026-10-16 on the fixed engine:** −₹31.6k P&L but DD 6.7→5.1%, Calmar 5.96→7.37 (best risk-adjusted result in the re-run) — the −₹69k "amputation" was the freeze artifact. Needs 4-half-year-window validation before enabling
- **Per-instrument rolling loss budget — FALSIFIED 2026-09-07, not built**: a 20%-of-notional budget per name over a trailing quarter (tighten the new lot's hard stop to the remaining budget, block entry when exhausted) was stratified on the ₹6L baseline (`scripts/name_loss_budget_study.py`): rounds entered with <25% budget left are the BEST bucket (avg ₹1,630, 71% win), and the static replay is negative at every window/budget/floor (−₹28k drawdown-ledger to −₹275k losses-only). Same failure as the cooldown/loss-block/discount guards — the rebuy after a loss stack is where the mean-reversion edge lives (QUESS: ₹38.5k → ₹11.2k). The per-name loss bound is the rolling stale re-arm, not the 20% stop. See `reviews/name_loss_budget_20260907.md`
- **Scale-in**: when `scale_in.enabled`, an ENTRY on an already-held instrument routes to `_validate_addon()` — geometric sizing off the previous lot, separate budget pool (`_scale_in_deployed`, on top of base capital), daily spacing, tier cap. See the Scale-in section

---

## OrderManager behaviour

- **Paper mode**: queues orders in `_pending_paper`; MARKET fills at next candle open, LIMIT fills only if price touches the limit level during a candle (low <= limit for BUY, high >= limit for SELL); fill price = limit price exactly
- **Live mode**: places order via `kite.place_order()` with `order_type=MARKET` (uses `market_protection=-1`) or `order_type=LIMIT` (uses `price=limit_price`); optionally places GTT OCO after BUY fill confirmation
- **EOD cancellation (LIMIT mode)**: unfilled LIMIT orders are cancelled at day boundary — `clear_pending()` dispatches CANCELLED for each so strategy clears `_entry_price` and risk releases capital
- GTT only placed on BUY/ENTRY orders, never on SELL/EXIT orders
- Dispatched fill records include `signal_type`, `target_price`, `partial` and `addon` from the original Order so callbacks can distinguish entry vs exit vs scale-out vs add-on fills (CANCELLED/REJECTED dispatches carry `addon` too — a cancelled add-on must never reset the parent position's strategy state)

---

## Backtest engine (`trader/backtest/engine.py`)

Shared by `backtest.py`, `calibrate.py`, `screen.py`; never called in live trading. Engine behaviours (intrabar SL/target, gap fills, LIMIT simulation, metrics, trade-record semantics): `trader/backtest/CLAUDE.md`.

- `store.clear_backtest_data()` — called at startup by `backtest.py`, `backtest_rolling.py` and `walk_forward.py` (never by the engine). **It wipes the entire local candle cache** — the next run re-fetches from Kite, so a valid access token is required after any of these scripts run

**UI (scripts/ui.py):**
- Tab 1 trade table shows `Hold (d)` (calendar days), `Candles` (held_candles), and `Capital` (effective capital at trade entry) side by side
- Tab 2 (per-instrument) also has the `Capital` column; both tabs support chart interaction:
  - **Box-select on equity curve** → filters trade table to the selected date range
  - **Click on entry/exit marker** → highlights the corresponding trade row in the table
- Tab 2 "Show model signals" adds a **per-candle P(min)/P(max) pane** (fixed 0..1 axis, threshold/veto/sell guides) plus crossing markers on the price chart. Scores prefer the backtest run's own `model_scores` sink (exact model output); the standalone `_run_signal_probe` (independent retrain, approximate) is the fallback when no run covers the instrument. Classification (`ENTRY`/`VETOED`/`PATTERN_TOP`) happens UI-side in `_classify_scores`
- Tab 3 hold-duration scatter uses candles on x-axis; hours shown in hover tooltip
- **No strategy-param inputs** — config/config.yaml is the source of truth; the run uses global params deep-merged with `per_stock_params` (incl. per-stock `timeframe`), exactly like `backtest.py`. The sidebar shows a read-only per-stock timeframe table.
- Instrument selection defaults to the full `watchlist` — matches `backtest.py` behaviour

---

## LRExtremaStrategy — deep dive (`trader/strategies/lr_extrema.py`)

### What it does
LRExtremaStrategy is a **self-training swing entry detector**. It learns what local price minima look like on a given stock using historical candles, then fires a BUY signal when the current candle looks like a local minimum — i.e., the price is likely near a short-term bottom and about to bounce.

The model retrains itself every `retrain_every` candles using the most recent history, so it adapts to the stock's current behaviour over time.

### How it works and config params

Step-by-step mechanics (features, entry gates, the three exit mechanisms, stale re-arm, retraining) and the param table: `trader/strategies/CLAUDE.md` (exit/entry policy code also lives in `trader/policy/`).

### Alternative detection stack (config-gated, default-off — 2026-07 regime campaign)

Swappable components behind nested config blocks; production defaults unchanged unless enabled:

- `labels.type: zigzag` — swing-pivot training labels by minimum-%-reversal (`labels.zigzag.reversal_pct`), no ATR. **`labels.zigzag.vol_scaled: {enabled, k, min_pct, max_pct}`** replaces the fixed percentage with `k × σ` (σ = std of bar-to-bar % returns over the training window) — label scale adapts per stock and per retrain window. Fixed percentages proved fragile (spike, not plateau); vol-scaled k∈[2.0, 2.5] is a plateau.
- `labels.neutral: {enabled, ratio}` — class-2 "neither" samples; fixes the forced P(min)+P(max)=1 split. Thresholds must be recalibrated when enabled (gbdt recipe uses 0.65/0.60).
- `labels.type: avg_trend` + `labels.avg_trend: {window, deadband_pct, stride}` — averaged directional labels (Bruni et al. 2026): class 0 if mean(close over next `window` bars) > mean(trailing `window` bars), else 1. **DENSE** — every eligible bar is a sample; the model becomes an Up/Down regime classifier whose Down→Up confidence flip is the entry event, so P(min) hovers near 0.5 and thresholds sit at 0.6–0.8, not 0.90. Lab metrics score dense labelers on class *transitions* (`Labeler.dense`, `scripts/lab/metrics.py::transition_indices`). **FALSIFIED as an entry detector 2026-07-16** — perfect label quality, but the model's Down→Up flip inherently fires ~window/2 bars past the turn (1.1–2.3% above trough on trends, gate ≤0.5%); it's a regime classifier, not a dip-timer. Dormant. Full results: `avg_trend_paper_plan.md`.
- `features.smoothing: {enabled, window: 21, edge: accel|constant|linear, slope_bars}` — causal Gaussian smoothing of the close channel (`trader/features/smoothing.py`, same paper) feeding the return-slope features and regime vector; norm_price/volume_ratio stay raw. Strictly causal: each bar's smoothed value uses only its past (acceleration-gated right-edge extension), computed once and cached by timestamp — deliberately NOT the paper's centered training smoothing, which would leak future closes into training features. **NULL on the winner recipe 2026-07-16** — parity within noise vs `winner_gbdt` (4 scenarios up, 3 down, both 7/7 PASS); dormant, not carried to backtest.
- `features.type: swing` — swing-position vector (`above_low_N`, `depth_N`, `ret_N`, `rsi_p`,
  `volume_ratio`; no bar-shape channel; `trader/features/swing_features.py`) and
  `entry_gates.turn: {lowest_of: N}` (fire on the first up-close after the lowest close of N bars).
  Built 2026-09-27 from the ATHERENERG hand-label forensic (`reviews/ather_minima_diagnosis_20260927.md`):
  the live P(min) is a "bar closed at its low" detector (norm_price corr −0.82; AUC 0.54 vs 191 human
  dips) while swing features rank at 0.69 and lift precision/recall from 38/27 % to 48/42 %.
  **FALSIFIED on P&L**: ATHER standalone ₹44.1k/Calmar 8.9 → ₹41.3k/5.3; portfolio with swing on the
  15m names only ₹498k/5.50 → ₹391k/3.46 (DD 8.0 → 10.2 %, utilisation unchanged). The extra catches
  are the shallow 2–3 % dips the exit stack kills through tier-1 stale. Better dip *identification*
  is not what the P&L rewards — the live model's bias toward deep close-at-low capitulation bars is a
  feature. Dormant, default-off; do not re-tune. The exit-side follow-up (arm the 2 % trail at
  +3 % instead of +7 %, with/without scale-out) is ALSO falsified: live entries ₹498k → ₹397k/₹424k,
  swing entries ₹391k → ₹358k/₹369k — the extra trailing exits are winners shaken out on 15m noise
  and the scale-out is starved; stale losses unchanged. Keep `profit_pct: 7` at 15m.
- `features.type: extrema_regime` + `features.regime.horizons: [...]` — appends efficiency-ratio / variance-ratio / slope-t-stat per horizon (`trader/features/regime.py`) so the model separates "dip in uptrend" from "falling knife" directly. Horizons are bar-counts — scale to the strategy TF (15m: 100/400/1600; day: 20/60/250).
- `model.type: gbdt` — HistGradientBoosting (depth 3). With clean sparse zigzag labels + long windows it beats logistic on trend scenarios (the old "GBM overfits" note was an artifact of noisy labels).
- `exits.trailing.regime_widening: {lookback_bars, min_slope_pct, trail_wide}` — widens the trail during a close-level uptrend. **Falsified at 15m** (EOD force-close binds first; overnight holds hurt) — dormant, do not enable at 15m.

**Detection campaign round 1 (TD-018, 2026-10-18) — every path in `reviews/extrema_campaign/LEDGER.md`:** against
"tradeable troughs" (dip reaches +profit_pct before the stock's own non-model exits fire) the production P(min) has
median AUC 0.511 and no label/feature/rule arm improves it (tradeable labels, lags, bar shape, ATR distance, S/R, OU,
rules, market features — all fail Stage A AND the full Stage-B backtest at matched thresholds (0/12 on P&L/DD/Calmar/
weighted win %); code on `exp/*` branches, not merged). Coin-flip controls (EXP-20/22): the model's ENTRY signal
carries the whole edge over random entries; the pattern-top signal is no better than a coin at the same rate. The one robust signal is market
timing — prior-day India VIX vs its trailing year (AUC 0.638, 6/7 years) — but threshold/size modulation by VIX state
did not survive the plateau check (`market_regime`, branch `exp/regime`). Do not re-run these arms; see
`reviews/extrema_campaign/CAMPAIGN_ROUND1_20261018.md`. Research tooling: `scripts/campaign/`.

Validated combination (see `reviews/dayw_candidate_proposal_20260713.md` and the lab in `scripts/lab/`): zigzag vol-scaled k=2.0 + neutral 2.0 + extrema_regime [20,60,250] + gbdt @ 0.65/0.60 on **day timeframe** for all names — Calmar 2.11, DD 10.8%, 6/7 rolling windows profitable incl. the 2025-H1 correction. Not deployed.

### What makes this strategy work (and when it fails)

**Works well on stocks that:**
- Exhibit clear mean-reverting or oscillating price behaviour — price bounces between loose support/resistance levels rather than trending strongly in one direction
- Have consistent volume patterns — volume spikes at local extrema (a key feature)
- Have moderate volatility — enough to reach the profit target within `hold_bars` candles without constantly hitting the stop
- Have sufficient liquidity — thin stocks have wide spreads and erratic candle patterns that confuse the features
- Are not in a strong one-directional trend — a stock in a confirmed uptrend may have very few "local minima" and the model won't generalise well

**Fails on stocks that:**
- Are strongly trending (all entries look like local minima in a falling market)
- Have extremely low volume / liquidity (penny stocks with days of zero volume)
- Have highly irregular candle patterns driven by news/events rather than technical structure
- Are in a prolonged sideways range so narrow that neither profit_pct nor stop_pct is reached within hold_bars

### Calibration (`scripts/calibrate.py`)

Grid or random search over all strategy params. Pre-fetches candles once; subsequent runs hit SQLite cache. Results ranked by `return_pct`. Runs combinations in parallel via `ProcessPoolExecutor` (uses all CPUs by default).

Use calibration to find the optimal parameter set for a specific stock before adding it to the watchlist.

```bash
python scripts/calibrate.py --from 2025-01-01 --mode random --iterations 100
python scripts/calibrate.py --from 2025-01-01 --mode random --iterations 100 --workers 4
python scripts/calibrate.py --from 2025-01-01 --params profit_pct stop_pct trail_pct  # vary only specified params
python scripts/calibrate.py --from 2025-01-01 --params sell_threshold veto_threshold min_hold_before_exit
```

Worker processes suppress all logging below `CRITICAL` (spawned processes don't inherit parent logging config)

### Screening (`scripts/screen.py`)

Backtests the current config params against all ~2,000 NSE EQ stocks. Resumable — already-processed symbols read from output CSV. Rate-limited to ~3 req/sec.

```bash
python scripts/screen.py --from 2025-01-01 --output results.csv --min-trades 3
```

---

## Stock selection

How to screen, interpret `screen.py` output, and shortlist watchlist candidates: the `stock-selection` skill (`.claude/skills/stock-selection/`). See also `discover`, `qualify`, `watchlist-review`.

## Costs (`trader/costs.py`)

`order_cost()` / `round_trip_cost()` in `trader/costs.py`. Covers: brokerage, STT, NSE transaction charges, SEBI charges, GST, stamp duty. CNC brokerage = zero.

**Cost dominance:** STT is 0.1% on both buy and sell sides for CNC (0.2% round-trip). A trade must move ~0.22% just to break even. Favour high-threshold, high-profit-pct params in calibration to keep trade count low and move size large.

**MIS vs CNC in backtest:** engine detects same-day entry+exit and applies MIS charges; multi-day positions use CNC charges.

---

## Notifications (`trader/notifications/telegram.py`)

Configured via `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. Safe to call when unconfigured (logs warning, no crash).

**Token reminder:** scheduler fires `notify_token_reminder()` at 08:30 IST daily — prompts to run `python scripts/kite_auth_server.py` on EC2 before market open.

---

## Cloud deployment (AWS EC2)

- Instance: t2.micro, ap-south-1 (Mumbai), Ubuntu 24.04 LTS
- Elastic IP: `13.202.187.191` — whitelist this in Zerodha API settings
- SSH port: 9654 (not 22)
- Service: `systemd` unit at `scripts/trader.service`, managed as `trader` user
- Deploy: `ssh trader "cd /opt/trader && sudo -u trader git pull && sudo systemctl restart trader"`
- Deploy with deps change: `ssh trader "cd /opt/trader && sudo -u trader git pull && sudo -u trader .venv/bin/pip install -r requirements.txt && sudo systemctl restart trader"`
- **The box is OFF outside trading hours (since 2026-09-05, cost: ₹1,660 → ~₹900/mo).** Started 06:45 IST Mon–Fri by EventBridge Scheduler `trader-start` (role `trader-ec2-scheduler`); powered off by the on-box `scripts/trader-poweroff.timer` at 16:00 IST Mon–Fri and 23:55 daily (catch-all), with EventBridge `trader-stop` at 16:00 as backup. **Releases just work:** `deploy.sh` runs `scripts/ec2.sh ensure-running` first (starts a stopped box, waits for SSH); the 23:55 timer stops it again. SSH/dashboard are unreachable while stopped. Elastic IP, EBS and host key survive stop/start. How-to + owed housekeeping (key rotation, detach AdministratorAccess): `aws_plan.md` → "Operations since 2026-09-05"; plan + implications: `infra_cost_plan.md`
- Token refresh: **boot-time** `scripts/kite-token-refresh.service` (oneshot, `RemainAfterExit`, retried every 120 s on failure; `trader.service` is `After=`/`Wants=` it) — every morning is a fresh boot. The 08:15 IST TOTP cron (`--no-restart`) stays as the independent second attempt; the bot hot-reloads `config/.env` at 09:00 either way. Manual fallback: `python scripts/kite_auth_server.py` on EC2
- KITE_ACCESS_TOKEN expires midnight IST — `scripts/kite_totp_refresh.py` does the TOTP login (boot unit + 08:15 cron)

---

## Live dashboard (`trader/ui/`)

Read-only Flask dashboard (loopback only; SSH tunnel / Tailscale). Full behaviour — auto-refresh, mobile layout, return stats + benchmarks, giveback pane, monthly card, range filter, positions, watchlist, drilldown, health strip: `trader/ui/CLAUDE.md`.

- **`render_page()` must never import from `trader.backtest`** — the live/UI path stays independent of the backtest engine; shared analytics live in `trader/analytics.py` (`match_trades`, `compute_utilisation`, `drawdown_stats`, `exit_reason_breakdown`, `per_stock_scorecard`).

## Known design decisions

- **Product is always CNC** (delivery) — hardcoded in `Config.product`. No intraday/MIS support.
- **Long-only** — all signals are BUY direction. No short selling.
- **Paper state is in-memory** — does not survive restarts. Live mode re-fetches from Kite on startup.
- **Paper fill timing** — ENTRY orders fill at next candle open (realistic slippage). EXIT orders (stop/target) are simulated intrabar in the backtest engine at the exact SL/target price; in live mode orders fill within seconds.
- **Strategy exit price_hint** — trailing/stop exits set `price_hint` to the tick `last_price` at the moment of exit; time-based (hold_bars) exits use candle close.
- **Tick-speed exits (`on_tick`)** — hard stop and trailing stop are checked on every raw Kite tick in live mode (~1 sec granularity). `on_candle` handles entry signals, hold_bars timeout, and pattern-top exit. In backtest the engine simulates ticks by calling `strategy.on_tick` with `candle["high"]` then `candle["close"]` per candle. Hard SL still fires intrabar at the exact low price via the engine's own check. Trailing exits record as reason `"TRAILING"` in the trades list. `_peak_close` (the trailing high-water mark) and the exit flags are persisted and restored across restarts (TD-002, TD-003).
- **Pattern-top exit** — fires in `on_candle` when `P(local-max) >= sell_threshold`, `held_bars >= min_hold_before_exit`, and `close > entry_price`. Reason: `"PATTERN_TOP"`. Does not fire when underwater — stop_pct handles that. Supplements trailing stop; both can be active simultaneously and whichever fires first wins. Features (return-based slopes + volume ratio) are the same as used for entry, making the model's buy/sell predictions symmetric.
- **Warmup phantom-state clearing** — both the backtest engine (`engine.py`) and live startup (`main.py`) feed historical candles through `on_candle` before trading begins; this can trigger signals that never receive a fill, leaving `_entry_price`, `_held_bars`, `_peak_close`, and `_trailing_active` in a stale state. Both paths explicitly clear all four fields when `_entry_price is not None and position is None` at the end of warmup, preventing phantom trailing-stop exits on the first real trade.
- **GTT is disabled (`gtt_enabled: false`)** — strategy exit logic (profit%, stop%, hold_bars) is the sole exit mechanism in live trading, consistent with backtest behaviour. GTT was disabled because: (1) backtest never uses GTT so enabling it creates a live/backtest divergence; (2) GTT-triggered exits were not confirmed via `on_order_update`, leaving strategy state inconsistent after a GTT fire. Safety net is `Restart=always` + `RestartSec=10` in the systemd unit — bot restarts within 10s on any failure and resumes exit monitoring on the next candle.
- **Scheduler timezone** — IST (Asia/Kolkata). Pre-market at 09:00, post-market at 15:35.
- **Pre-close flush beats the Closing Auction Session (15:29:15)** — Zerodha rejects every new order placed 15:30–15:35 (CAS). A decision on the last 15m candle (15:15–15:30, emitted at 15:30:00) therefore always died: CGPOWER 2026-08-27 lost a 50% pattern-top scale-out this way, TVSMOTOR 2026-08-17 a timeout exit. `LiveFeed.flush_open_partials_early()` (scheduler `pre_close`, 15:29:15, registered only for intraday base TFs) delivers every still-open partial as the decision candle ~45s early and flags it; the bucket's real completion (15:30 `flush_partials` / next rollover) is emitted with `_early_final: True`, which `handle_candle` persists (cache parity with Kite history) but never decides on. Backtest is unaffected (it decides at candle close anyway).
- **CAS-eligible stocks decide at 15:14:15 (2026-10-12)** — since 2026-08-03 NSE runs a Closing Auction Session for every stock with active derivatives: continuous trading ends at **15:15**, fresh orders are blocked 15:15–15:20 (Kite refuses synchronously: *"Your order could not be converted to a After Market Order (AMO)"*), and the 15:15–15:30 bucket is a flat, near-zero-volume auction candle. The 15:00 candle closes at 15:15:00 and day/4hour bars emit on it, so every decision on those names died (12 rejects Aug 31–Oct 12: CUMMINSIND day-TF entries 4 sessions running, ATHERENERG scale-out 10-12). Fix: `main.py::refresh_auction_set()` (every pre_market, from `kite.instruments("NFO")` FUT underlyings ∩ watchlist) → `LiveFeed.set_auction_tokens()`; scheduler `pre_auction` (15:14:15) → `LiveFeed.flush_auction_partials_early()` delivers those names' 15:00 candle ~45s early (real completion re-emitted `_early_final`, persist-only); their ≥15:15 bucket is always persist-only and skipped by the 15:29:15 pre_close flush. Unknown set (NFO fetch failed, no previous set) → pre_auction early-emits every stock and pre_close keeps its all-stock behaviour. Known gap: tick exits (trailing/hard stop) on CAS names after 15:15 still get refused (state restored, retried next session). `tests/test_closing_auction.py`.
- **Signals table reflects broker refusals** — `log_signal` writes `accepted=1` at risk approval, before placement. On any REJECTED dispatch (sync refusal with no order id, or async postback) `handle_order_update` calls `store.mark_signal_broker_rejected()`, flipping the instrument's latest accepted same-direction row to `accepted=0`, `reject_reason="BROKER: <kite message>"` (UI shows exit_reason — reason). Async reject records now carry `status_message`. `main._place_order()` swallows the post-dispatch re-raise from `OrderManager._place_live` so a refusal no longer aborts the rest of the candle/tick handler.
- **Feed reconnect is self-healing, not suspend-gated (2026-08-28)** — a 01:33 IST restart connected the ticker on the previous day's token; the token died at midnight, kiteconnect burned its 50 retry attempts on 403s and gave up, and 09:00 `pre_market()` rebuilt the ticker with the fresh token but `feed.reconnect()` no-op'd because `_suspended` was False (`disconnect()` had never run in that process). Zero ticks all session, 8 positions unmonitored. Fix: `LiveFeed.reconnect()` now connects whenever `_ticker.is_connected()` is False (or the feed was suspended / the ticker was just rebuilt), stays a true no-op when the socket is live or before `start()` (main.py's startup calls `pre_market()` → `reconnect()` *before* `feed.start()`, guarded by `_started`), and always clears `_suspended`. `update_access_token()` only rebuilds + arms `_needs_reconnect`; it tears the old ticker down unconditionally (`close()` + `stop_retry()`), since `is_connected()` is False while a 403 retry loop is still running. `tests/test_live_feed_reconnect.py`.
- **Rejected EXIT restore covers scale-outs** — a PARTIAL (`PATTERN_TOP_PARTIAL`) emission consumes one-shot guards (`partial_taken`, `pattern_top_trailing`, arms the remainder trail) without resetting the position, so it takes `PositionState.snapshot()` (capture, no reset) before mutating; a REJECTED/CANCELLED exit restores it via the same `restore_snapshot()` path as full exits, and a COMPLETE partial fill clears it. Without this, a rejected scale-out left the whole lot on the tight remainder trail with the scale-out permanently disarmed. `tests/test_exit_reject_restore.py`.
- **Pre-order cash check (2026-10-17, TD-001)** — before every live ENTRY (parent or add-on) `main._place_order` reads Kite `net` (`_fetch_kite_cash`); if it can't fund qty × price × 1.01 (`risk.manager.unfunded_entry`) the order is NOT sent: pending lock released, signal row stamped `insufficient_cash: need/have` (`store.mark_signal_rejected`), entry guard cleared via `on_pre_order_reject(signal, "insufficient_cash")` so the next candle retries. No broker reject, no Telegram, no block. Skip, never clamp; fail open when margins fail. Backtest/paper unaffected.
- **Pre-order risk rejects clear the entry guard (2026-10-16)** — strategies arm their pending-entry guard when they EMIT an ENTRY and clear it on the order's fill/REJECTED/CANCELLED update. A `risk.validate()` refusal (quantity_zero, max_positions, stock_paused, daily_halt, slow_tf_limit, …) never produces an order, so no update arrived and the stock went silent — for the rest of a backtest (one `quantity_zero` froze QUESS/TVSMOTOR/SCHAEFFLER Jan→Oct in the 2026 YTD run; adding 3 names read −₹9.3k instead of +₹14.4k), until restart live. `Strategy.on_pre_order_reject(signal, reason)` routes those through the normal REJECTED path; the engine's `_process_decision` and both live paths in `main.py` call it. Kept armed for `already_in_position` / `pending_order_exists`; EXITs and in-position add-on ENTRYs untouched. Every capital-crowded backtest before this fix is path-dependent noise — re-run before trusting it. `tests/test_pre_order_reject_guard.py`.
- **Backtest engine is backtest-only** — `trader/backtest/engine.py` is never imported in live trading paths.
- **Effective capital in live mode** — on startup, `main.py` fetches `kite.margins(segment="equity")` (free cash = `net`, falling back to `available.live_balance` → `available.cash`; `available.cash` is the OPENING balance and would double-count same-day buys after a mid-session restart — ISS-01, `risk.manager.free_cash_from_margins`) and applies `effective_capital = min(config.total_capital, kite_available_cash)` via `config.set_effective_capital()`. This ensures the bot never tries to deploy more money than is actually in the account while still respecting the config ceiling. All derived values (`daily_loss_limit`, `max_risk_per_trade`, `max_capital_per_stock`) update automatically since they derive from `config.total_capital`. Paper mode is unaffected — it always uses the config value as-is. If the margins call fails, the system falls back to config capital and logs a warning.
- **Cumulative P&L persistence** — `RiskManager._cumulative_pnl` is persisted to the SQLite `state` table (key `cumulative_pnl`) in live mode via `store.set_state()` on each close. On startup, `main.py` restores it via `risk.seed_cumulative_pnl(store.get_state("cumulative_pnl"))`. This ensures `capital_available` is correct across restarts (deployed capital freed + lifetime P&L tracked). Paper mode does not persist — resets to 0 on restart.
- **`state` table in SQLite** — `store.get_state(key, default=0.0)` and `store.set_state(key, value)` provide a simple key/float persistence layer. Used for `cumulative_pnl` and per-stock pause flags (`<instrument>.paused`).
- **`model_scores` table in SQLite** — persists the model's `(p_min, p_max)` per candle for the dashboard's conviction-trajectory sparkline. Written in `main.py`'s `handle_candle` once the model is trained, via `store.write_model_score(instrument, timestamp, p_min, p_max)` (keyed on `(instrument, timestamp)`, trimmed to the last 500 rows per instrument). Read by the UI via `store.get_model_scores(instrument, limit)`. **Warm-up backfills the trailing 80 candles** (`_CONVICTION_BACKFILL` in `main.py`) so the sparkline is populated immediately on startup rather than growing in over the first ~80 live candles; because the model retrains progressively through warm-up, each backfilled score mirrors what live would have recorded at that point (no seam with the live points that follow). Only the trailing window is persisted — the sparkline shows 80, and writing all ~1,200 warm-up candles per symbol would be wasteful. The write is wrapped in try/except — purely cosmetic, a persistence failure never disturbs warm-up or the trading path. Backtest never writes it (consistent with "engine is backtest-only").

---

## Zerodha CNC order EOD rules (important)

| Order type | Used by this system | EOD behaviour |
|---|---|---|
| CNC Limit | Yes (when `order_type: limit`) | Cancelled at 3:30 PM if unfilled — simulated in backtest at day boundary |
| CNC SL / SL-M | No | Cancelled at 3:30 PM — must re-place next day |
| CNC Market | Yes (when `order_type: market`) | Fills immediately during market hours — no cancellation risk. **Rejected outright 15:30–15:35 (CAS)** — hence the 15:29:15 pre-close flush. **F&O-eligible stocks: rejected from 15:15** (auction transition) — hence the 15:14:15 pre-auction flush |
| GTT (Good Till Triggered) | **Disabled** (`gtt_enabled: false`) | Persists across days — not cancelled at EOD |

**Paper vs live simulation mismatch for end-of-day signals:**
In live mode a market order placed at e.g. 15:15 fills within seconds (same day). In paper mode the same signal queues and fills at the **next candle's open** (next trading day 09:15 if it's the last candle of the day). This means:
- Paper mode overstates overnight gap risk for entry signals that fire during market hours
- Backtest P&L will be slightly more pessimistic than live for late-day entry signals
- This is an accepted approximation — fixing it would require intraday fill simulation
