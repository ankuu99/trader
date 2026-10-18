# Strategy S0 — lab portfolio simulator (model-agnostic: scores in, ₹ curve out)
Written: 2026-10-18 · Tag: TD-023 · Status: TO DO

## Source

> while these are runing ,can we start on the strategy framework aroud this, what would that look like? ahve we
> thought of it yet? will these be baked into current framework? should we braistom on that or it is of no use utill
> we get a stable model ?

> day and 15 min both. whoele universe, with exclusion lists on really bad stocks, this list could be reviesed. first
> it will run on its own with its own capital, then depdending on performance we can switch off lR extrema or this one
> ain a few months.

— `TODO/TD-023-strategy-framework-for-lab-models/DETAIL.md`, as of 2026-10-18. Design: `docs/04_Strategy_Framework_Proposal.md`
(phase S0). Owner go-ahead for this spec: 2026-10-18 ("Yes, let go ahead").

## Intent

An offline, walk-forward portfolio simulator for the Model Lab. It reads a lab run's out-of-sample scores (or a
reference score on the same rows, e.g. a coin), and simulates a single capital sleeve: each decision time it ranks the
eligible stocks, fills free equal-₹ slots, and exits through a small exit library. Output: trades, a daily equity
curve, money metrics, a markdown report. It is **model-agnostic** and **causal** (nothing at time t uses data after t).

**Must NOT change:** any existing lab module's behaviour, the run-directory contract, anything outside
`research/model_lab/` and the named tests. `research/model_lab/` keeps its rule of no imports from
`trader.strategies`, `trader.features`, `trader.policy`, `trader.backtest`; **`trader.costs` IS allowed** (pure
function, no config). Do NOT run on real data; do not touch `lab_data/` (a background run is writing there).

## Implementation steps

New module `research/model_lab/portfolio.py` (+ `paths.PORTFOLIOS_DIR = LAB_ROOT / "portfolios"` in `paths.py`).

1. **Config** — a frozen dataclass `SimSpec`:
   - `sim_id: str`, `run_id: str`, `score_source: str = "run"` (`"run"` = the run's `score` column; `"ref:<name>"` =
     `references.read_ref(tf, name, sym)["score"]` aligned by timestamp to the run's scored rows — same symbols and
     timestamps as the run, only the score differs; `"pred:<col>"` = that `pred_*` column of the run's scores).
   - `capital: float = 600_000`, `slot: float = 40_000` → `n_slots = int(capital // slot)` (fixed ₹ per slot, no
     compounding in S0).
   - `entry_mode: str = "rate"` (`"rate"` | `"topk"`), `rate: float = 0.01`, `window_sessions: int = 60`,
     `topk: int = 0` (topk mode: at each decision time the K best-scoring eligible names are candidates, no threshold).
   - Exits (any may be None = off): `stop_pct`, `target_pct`, `trail_pct`, `trail_activate_pct = 0.0`,
     `hold_bars` (required, the time stop), `reentry_gap_bars: int = 0`.
   - `exclusions: tuple = ()` — tuples `(symbol, from_date, to_date|None)`; a symbol is ineligible for NEW entries on
     dates in `[from, to]` (point in time; existing positions are not force-closed).

2. **Data assembly** — for the run (`paths.RUNS_DIR / run_id`, `meta.json` gives `tf` and symbols): per symbol load
   `bars.load(sym, tf)` and the scores parquet; map each scored row to its bar index (`pd.Index(timestamps)
   .get_indexer`), drop unmatched. Keep per-symbol numpy arrays (open/high/low/close, timestamp, score at bar or NaN,
   fold_id). Eligible rows = rows with a non-NaN score (the run's PIT universe) and not excluded on that date.

3. **Causal threshold (rate mode)** — the threshold for every decision time on calendar date D is the
   `(1 − rate)` quantile of **all eligible scores pooled across symbols at decision times on the previous
   `window_sessions` distinct calendar dates strictly before D** (recomputed once per date, not per bar). Fewer than
   `window_sessions` prior dates → no entries that date (warm-up). The window crosses fold boundaries (documented:
   score scale may shift when the model is refit; the report states it). A row is a candidate when score ≥ threshold.

4. **Event loop** — decision times = sorted union of all bar timestamps. At decision time t (bar close):
   a. **Exits first** for every open position whose symbol has a bar at t (positions with no bar at t are untouched):
      evaluated on bar t (the bar after entry is the first eligible; entry bar included — see e),
      in this order, first hit wins:
      - `stop_pct`: `low ≤ entry_px·(1−s)` → fill at `min(open, stop_px)` if the bar is not the entry bar, else
        `stop_px` (entry bar opened at entry_px); reason `STOP`.
      - `target_pct`: `high ≥ entry_px·(1+x)` → fill at `max(open, target_px)` (same entry-bar rule); reason `TARGET`.
        **Same bar hits both → STOP** (the T5 barrier convention).
      - trailing: track `peak_close` (max close since entry, including bar t). If `trail_pct` set and
        `peak_close ≥ entry_px·(1+trail_activate_pct)` and `close ≤ peak_close·(1−trail_pct)` → mark to exit at the
        **next bar's open** of that symbol; reason `TRAIL`.
      - time stop: `held_bars ≥ hold_bars` → fill at bar t's **close**; reason `TIME`. `held_bars` counts bars from
        the entry bar inclusive (entry bar = 1), so `hold_bars = H` with no other exit reproduces `t5_ret_H{H}`
        (entry at open of signal bar + 1, exit at close of signal bar + H).
      - Pending marked exits (TRAIL) fill at the open of the symbol's next bar before anything else on that bar.
   b. **Entries**: candidates = eligible rows at t that pass the threshold (rate mode) or are the top K (topk mode),
      excluding symbols currently held, with a pending entry, or within `reentry_gap_bars` bars of their last exit.
      Rank by score descending, ties by symbol ascending. Free slots = `n_slots − open − pending`. The top
      `free` candidates get a **pending entry filled at the next bar's open of that symbol**; quantity =
      `floor(slot / open_px)`; quantity 0 → skipped (logged as `qty_zero`, slot freed). A pending entry whose symbol
      has no further bar is dropped.
   c. End of data: open positions are closed at their last bar's close, reason `END`.

5. **Costs** — per trade `trader.costs.round_trip_cost(product, qty, entry_px, exit_px)` with product `"MIS"` when
   entry and exit fall on the same calendar date, else `"CNC"` (the backtest engine's convention). `net = gross − cost`.

6. **Outputs** — `PORTFOLIOS_DIR / sim_id /`:
   - `trades.parquet`: symbol, signal_ts, entry_ts, entry_px, exit_ts, exit_px, qty, reason, held_bars, gross, cost,
     net, ret_pct (net / (qty·entry_px)), fold_id, score.
   - `equity.parquet`: one row per calendar date: realised cumulative net, open mark-to-market (at that date's last
     close), equity = capital + realised + MTM, deployed ₹ (Σ qty·entry_px of open positions), utilisation =
     deployed / capital, open positions.
   - `summary.json` and `reviews/model_lab/portfolios/<sim_id>.md` (`report_portfolio()`), containing: total net ₹,
     trades, win rate, profit factor PF = Σwins/|Σlosses|, **money-weighted win % = PF/(1+PF)**, avg net ₹/trade,
     max drawdown (₹ and % of peak equity, from the daily equity series), annualised return % on capital, Calmar =
     annualised return % / max DD %, mean utilisation, avg held bars, exits by reason (counts and ₹ — counts only, no
     per-reason win rates), a **per-calendar-year table** (trades, net ₹, max DD %), the same headline line **excluding
     2020**, and the spec as JSON. Header line: "Offline lab simulation — survivor-biased universe (TD-022); not a
     production backtest."
   - CLI: `python -m research.model_lab.portfolio --run <run_id> --sim-id <id> [--score-source run|ref:coin|pred:...]
     [--rate 0.01] [--hold-bars 20] [--stop-pct ..] [--target-pct ..] [--trail-pct ..] [--trail-activate-pct ..]
     [--capital 600000] [--slot 40000] [--entry-mode rate|topk] [--topk K]`. Percent arguments are fractions
     (0.05 = 5 %).

7. Pure helpers exposed for tests: `causal_thresholds(dates, scores, rate, window) -> dict[date, float]`,
   `money_metrics(trades_net: np.ndarray, equity: pd.Series, capital: float, years: float) -> dict`.

## Tests required

New `tests/test_model_lab_portfolio.py` (synthetic data only, tmp lab root via monkeypatching `paths`, as the existing
lab tests do):
- `test_time_exit_reproduces_t5_ret` — one symbol, `n_slots` large, only `hold_bars = H`, rate mode replaced by
  `topk=1`: every trade's gross return (exit/entry − 1) equals `targets.build_targets(...)["t5_ret_H{H}"]` at its
  signal row (rtol 1e-12) for H on the TF's grid (use a non-grid `hold_h` override only if needed).
- `test_hand_toy_portfolio` — 2 symbols, 1 slot, hand-built bars and scores: the higher score is chosen; stop with a
  gap-down open fills at the open; target with a gap-up fills at the open; a bar hitting both → STOP; trailing exit
  fills at the next open; the freed slot is reused the next decision time; all ₹ values hand-computed in the test.
- `test_threshold_is_causal` — changing scores on or after date D leaves the thresholds for dates ≤ D unchanged
  (strictly-before window), warm-up dates have no threshold.
- `test_no_lookahead_in_trades` — perturbing bars strictly after a trade's exit leaves that trade identical.
- `test_costs_mis_vs_cnc` — same-date round trip charged MIS, overnight charged CNC (values from `trader.costs`).
- `test_exclusion_point_in_time` — excluded symbol gets no new entries inside its date range, entries before/after OK,
  an open position is not closed by the exclusion.
- `test_score_source_ref_and_pred` — `ref:coin` uses the same rows as the run (same eligible set, different scores);
  `pred:<col>` reads that column.
- `test_money_metrics_hand_case` — PF, PF/(1+PF), max DD ₹/%, Calmar on a hand equity series.
- `test_no_forbidden_imports` — `portfolio.py` imports nothing from `trader.strategies/features/policy/backtest`.

Suites that stay green: the full suite.

## Acceptance checklist
- [ ] full pytest green (known pre-existing fail: ISS-11 during 09:15–15:30)
- [ ] time-only exit reproduces `t5_ret_H` exactly; hand toy portfolio matches to the paisa
- [ ] thresholds strictly causal (previous `window_sessions` dates only); warm-up enters nothing
- [ ] entries at next bar open; stop/target gap fills at the open; same-bar stop+target = STOP; trail exits next open
- [ ] costs via `trader.costs.round_trip_cost`, MIS iff same calendar date
- [ ] report has money-weighted win %, max DD, Calmar, utilisation, per-year table, ex-2020 line, survivorship header;
      no per-exit-reason win rates
- [ ] no imports from `trader.strategies/features/policy/backtest` in `research/model_lab/`
- [ ] Do NOT run on real data; do not touch `lab_data/`

## Out of scope (later phases, docs/04)
Model-driven exits from `pred_*` quantiles (S3), VIX market filter variant, pain-scaled sizing, scale-in, the
exclusion-list rules themselves (file + criteria — owner to pick), survivorship correction (TD-022), live adapter (S4).
All are TD-023 phases, not new TDs.

## Completion record
_(filled by the main session after validation)_
