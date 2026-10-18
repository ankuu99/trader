# Model Lab — a vanilla turning-point framework outside LR-Extrema (TD-021)

**Status (2026-10-18): SCOPE APPROVED by the owner, nothing built yet.** The owner answered the open questions
(§ "Owner decisions"). The next session starts at § "Start here". Tracker: `TODO/TD-021-model-lab-outside-lr-extrema/`.

## Why

Round 1 of the detection campaign (TD-018, `reviews/extrema_campaign/CAMPAIGN_ROUND1_20261018.md`) tested 12 ideas
against the production entry model, and none beat it, either on the ranking test or in the full backtest. The owner's
critique (2026-10-18), which is correct: every one of those ideas lived **inside LR-Extrema's construct**:

- one model per stock;
- a ~1,200-bar rolling training window (≈ 7 weeks of 15m bars);
- labels that mark only the extreme bars of a fixed-order window;
- a probability threshold tuned to the logistic scale;
- features computed by the strategy's own pipeline.

Round 1 shows that *tweaks to that construct* don't help. It does not show that no model can find turning points
better. Also note that the coin-flip controls (EXP-20/22) do NOT say the model is a coin:

- its **entry** signal clearly beats random entries (₹439k vs ₹158–389k, DD 5.8 % vs 8–13 %, weighted win 63.9 % vs
  55–61 %);
- only its **pattern-top** signal is no better than a coin at the same rate.

The production P(min) is therefore the bar to beat, not a strawman.

## Nomenclature (owner, 2026-10-18, DECISIONS)

- **Model** — the mathematical / ML tool that looks at the data up to candle *t* and says whether *t* is a good entry
  (local min) or exit (local max) point, and what the coming move looks like (size, timing).
- **Strategy** — everything around it: stop loss, target, trailing, stale/early exits, minimum hold, scale-in/out,
  risk sizing, capital limits.

The lab evaluates **models only**, with the strategy held fixed (or replaced by a neutral grid of exit rules). A model
moves into the strategy only after it wins in the lab.

## Owner decisions (2026-10-18)

| # | Question | Owner answer | What it means for the build |
|---|---|---|---|
| D1 | Data access | Free to pull fresh data from Kite with the standard auth whenever needed | Expired token → `.venv/bin/python scripts/kite_totp_refresh.py --no-restart` (pre-authorised, see memory). Fetch via `trader.data.historical` helpers. |
| D2 | Forecast horizon | Predicting forward need not be one candle at a time; the forward path also tells the **hold period and the potential** | Multi-horizon targets: the forward path, time-to-peak (implied hold), MFE/MAE within the horizon (potential vs pain). See § Targets T4–T5. |
| D3 | Universe | **All stocks are candidates** | Not limited to the 21 watchlist names or the 105 cached ones: any NSE EQ symbol. Staged fetch order in § Data. |
| D4 | Timeframes | **All timeframes** | 15m, 30m, 60m (native Kite), 4h and day (ours: `CandleAggregator` boundaries or native day), weekly from day. Each is a separate panel; cross-TF features are allowed. |
| D5 | Definition of a min/max | **Both**: a ±*w*-bar window AND a %-reversal zigzag (vol-scaled) | Two target families, scored separately, never mixed. |
| D6 | Date splits | **Dynamic, not one fixed split** | Several split schemes and many folds (§ Protocol); a result counts only if it holds across folds and years. |
| D7 | Non-stationarity | "A lot methodologically would have changed year on year" | Per-year and per-regime reporting, recency weighting, a known structural-break list, and the training-window length treated as a tuned choice. |
| D8 | Tooling | Free to install torch locally | `torch` 2.14.1 installed in `.venv` (Apple MPS GPU available). Lab-only, NOT in `requirements.txt` (the EC2 t2.micro never runs it), listed in `requirements-lab.txt`. lightgbm needs Homebrew `libomp`, so it was not installed; xgboost 1.7.6 + sklearn 1.8 cover trees. |
| D9 | Session | The owner starts the build in a new session | This doc is the hand-off; § "Start here". |

## The framework

### 1. Data (read-only reuse of the current data layer; no strategy code)

**Already cached** in `data/market.db` (2026-10-18):

| Series | Depth |
|---|---|
| 15m OHLCV, 105 NSE stocks | 22 from 2017–19, 5 from 2021, 50 from 2023, 28 from 2024+ |
| Daily OHLCV, 532 stocks | from 2023-06 |
| Nifty 50 + India VIX 15m | 2019-06 → 2026-10-16 |

**Fetching more (D1, D3):**

- `trader.data.historical.get_candles(kite, store, token, "NSE:SYM", tf, from, to)` caches and returns.
  `_fetch_and_cache` fetches an explicit range in chunks: 60 days per request intraday, 2,000 days for day, with a
  rate-limit backoff. Template: `scripts/campaign/backfill_regime.py`.
- **Gotcha:** `get_candles` only fills the gap AFTER the latest cached candle, so it never backfills earlier history
  for a symbol that is already cached. Use `_fetch_and_cache` for explicit older ranges, as `backfill_regime.py` does.
- **Gotcha:** `backtest.py`, `backtest_rolling.py` and `walk_forward.py` call `store.clear_backtest_data()`, which
  **wipes every candle in the DB they point at**. The lab must keep its own store,
  `lab_data/model_lab/candles.db` (a `Store` on a separate path), so a backtest run can never delete the lab's history,
  and the lab never writes into `data/market.db`.
- **Gotcha:** off-grid 15m rows (15:16–15:25) exist in EC2-sourced data (ISS-12); filter to the 15m grid on load.
- **Budget:** Kite allows ~3 historical requests/second. All ~2,000 NSE EQ names × 9 years of 15m ≈ 2,000 × 55 chunks
  ≈ 110k requests ≈ 10+ hours. Daily is ~2 requests per name. So stage it:
  1. the 105 cached names (top up to the latest date);
  2. daily for all NSE EQ (cheap, gives the universe filter);
  3. 15m for a liquid universe chosen by a **point-in-time** rule (e.g. median traded value over the prior year, not
     today's ranking);
  4. extend 15m coverage as results justify.
- **Survivorship:** `kite.instruments("NSE")` lists only currently listed names, so delisted or suspended stocks are
  missing. The universe is survivor-biased; record it as a known limitation and prefer point-in-time liquidity
  filters over present-day lists.
- **Hindsight:** the 21 watchlist names were picked knowing 2023–26 outcomes. Never select the training or test
  universe with them; score them as a subset only.

**Addendum 2026-10-18 (L0 build):** the lab store is zstd **parquet** per (interval, symbol) under
`lab_data/model_lab/bars/`, not a second SQLite `Store` — the laptop had 7.8 GB free (DECISIONS 2026-10-18). Kite 15m
history starts in early 2015; day goes back past 2008. 3,050 plain NSE EQ symbols (no `-` suffix), ~369 of them
ETF-like. Specs: `to_develop/2026-10-18_TD-021_L0a-*.md`, `…_L0b-*.md` on branch `exp/model-lab`.

### 2. Factor library: every candle property is its own time series

All factors are strictly causal (from bars ≤ *t*), computed per timeframe, and stored as
`(stock, timeframe, timestamp) → factor columns` (parquet under `lab_data/model_lab/factors/`).

- **Raw:** open, high, low, close, volume; gap from the previous close.
- **Shape:** body, upper and lower wick, close location in the range, range / ATR.
- **Returns:** many horizons (1, 4, 16, 64, 256 bars), log-return z-scores.
- **Position:** distance to the rolling min/max over many windows (20 … 1,000 bars); drawdown from high; bars since the
  last N-bar low/high; RSI / stochastic-type oscillators.
- **Volatility:** realised volatility at several horizons; vol-of-vol; ATR; range expansion.
- **Volume:** relative volume, volume z-score, up-volume vs down-volume, volume on the low bar.
- **Multi-timeframe (D4):** the same factors from higher timeframes, joined to each bar using only completed
  higher-TF bars.
- **Calendar:** time of day, day of week, days to month-end / expiry, session position.
- **Market:** Nifty and VIX returns, drawdown and percentile vs trailing year (the one robust round-1 signal, AUC 0.638);
  the stock's beta and residual return vs Nifty.
- **Cross-section:** the stock's return rank across the universe at that bar; market breadth (share of the universe
  above its N-bar mean).
- **Sequences:** raw windows of the last *L* bars, normalised causally, for sequence models.

### 3. Targets (hindsight labels, used only for training and scoring)

| ID | Owner question | Target |
|---|---|---|
| T1w | Is *t* a potential min / max? (window) | *t*'s low is the lowest low within ±*w* bars (several *w* per TF); same for max |
| T1z | Is *t* a potential min / max? (zigzag) | *t* is a zigzag pivot with a reversal ≥ *k*·σ (σ = trailing bar-return std; several *k*) |
| T2 | Will the direction change? | Sign of the forward trend vs the backward trend over *h* bars, with a dead-band |
| T3 | By how much? | Size of the move from *t* to the next opposite pivot (% and in σ units) |
| T4 | Forward path (D2) | Forward return at horizons *h* ∈ {1, 2, 4, 8, 16, 32, 64, 128} bars (per TF), as quantiles; optionally the whole path (seq2seq) |
| T5 | Hold period and potential (D2) | Within horizon *H*: MFE (max rise from close[*t*]), MAE before the MFE, **time-to-MFE** (implied hold), and P(+X % before −Y %) on an X/Y grid |

T5 matters most for money. Round 1 showed that a dip which turns but first falls another 5 % is killed by the
strategy's exits, and that the hold length decides whether stale exits fire. Labels are attached to bar *t* but use bars
up to *t*+*H*; that horizon sets the embargo below.

### 4. Protocol: dynamic splits, walk-forward, non-stationarity (D6, D7)

The lab never relies on one split. Every model is run under several schemes, and results are reported per fold:

- **Expanding walk-forward:** train on everything before fold *k*, test on fold *k*; folds are quarters or
  half-years and step through the whole history.
- **Rolling walk-forward:** fixed training windows of several lengths (e.g. 6 months, 1, 2 and 3 years). Window length
  is a tuned choice, picked by an inner walk-forward, never on the test fold.
- **Anchor sweep:** the same model trained from different start years, to see whether old data helps or hurts.
- **Leave-one-year-out:** a **diagnostic only**, since training on the future to test the past leaks regime knowledge.
  It answers "is year X just different?".
- **Held-out stocks:** each scheme also scores names absent from training (stock-group splits nested inside the time
  splits).

Rules for every scheme:

- **Point-in-time inference.** At test bar *t* the model sees only bars ≤ *t*. Predictions for a whole test fold are
  produced bar by bar, or vectorised with a check that matches the bar-by-bar output.
- **Purge + embargo.** Training samples whose label window overlaps the test fold are dropped, plus an embargo of *H*
  bars (López de Prado ch. 7).
- **Time-aligned pooling.** In a pooled model a fold is a time range for ALL stocks, so no stock's future leaks into
  another stock's past.
- **Recency weighting** as an option (exponential decay over sample age), compared against no weighting.
- **Normalisation fitted on training data only**, refit per fold.

**Reporting non-stationarity (D7):**

- per calendar year;
- per market regime (VIX tercile, Nifty trend up/down/flat);
- per timeframe and per stock-liquidity bucket.

A model wins only if its curves dominate production P(min)'s (§6) in most folds AND most years, not just on the pooled average.
Also track feature-importance drift across folds: a factor that matters only in one era is a red flag.

**Known or suspected structural breaks** to mark on every per-year chart (verify the dates before relying on them):

- COVID crash and recovery (Feb–Jun 2020);
- the T+1 settlement rollout (completed Jan 2023);
- SEBI's F&O weekly-expiry rationalisation (late 2024) and higher F&O STT (Oct 2024), which change index-option-driven
  intraday flows;
- the NSE closing-auction session for F&O-eligible stocks (2026-08-03, see CLAUDE.md "CAS");
- the bot's own universe changes (watchlist history).

### 5. Model ladder (cheap to expensive)

1. **Naive baselines:**
   - a coin at the same firing rate;
   - lowest-of-N turn;
   - RSI;
   - **the production LR-Extrema P(min)**, the reference to beat on the §6 curves. Scores 2023-01 → 2026-10-16 are
     cached at `lab_data/campaign/scores/<label>.pkl` for the 21 watchlist names (TD-018 Stage A); L1 replays the
     model (`score_current`, position-independent) on the lab's bars for any stock and range.
2. Pooled logistic regression on the factor library.
3. Gradient-boosted trees (sklearn HistGradientBoosting, xgboost). Classifiers for T1/T2, quantile regressors for
   T3–T5.
4. Sequence models (`torch`, MPS): 1D-CNN / TCN / LSTM / small transformer on raw windows. Multi-task heads: T1 +
   T4 quantiles + T5.
5. Later, optional: pretrained time-series foundation models as feature extractors (evaluate only if 3–4 show signal).

Per-stock vs pooled vs pooled-with-stock-embedding is itself an arm.

### 6. Scoring: the model on its own terms (owner, 2026-10-18 — supersedes the matched-rate / production-exit gate)

The strategy does NOT judge the model. No matched pick counts, no production exits as the referee: a model that finds
more good entries and exits is better, full stop. Hindsight truth (§3) is the referee, and every model is shown across
**all** firing rates (thresholds), so firing more is never penalised by construction. The strategy is designed later,
around what the winning model predicts.

- **Finding turning points (T1w, T1z), as curves over the firing rate:**
  - event recall: share of true pivots caught (a firing within a small tolerance window of the pivot);
  - precision: share of firings that are a true pivot (within the same tolerance);
  - lateness: bars between the true pivot and the firing;
  - entry distance: % above the true low (below the true high for tops).
- **Will the direction change, and by how much (T2, T3):** classification curves for the turn; rank correlation and
  calibration of the predicted move size vs the realised one.
- **Forward path (T4, T5):** predicted potential (MFE), pain (MAE before the MFE) and time-to-peak (hold period) vs
  realised — rank correlation, quantile calibration (pinball loss, coverage); hit-rate curves for +X % before −Y %.
- **Measurement rules (not restrictions):**
  - **events, not bars** — consecutive firings on the same dip count as one catch, so clustering cannot inflate
    "more entries";
  - **net-of-cost view** — every pick also shows its move net of ~0.22 % round-trip cost (entry at the next open), as
    an informational column, never a pass condition.
- **References on the same charts:** production LR-Extrema P(min) (replayed on the lab's bars for any stock; on TFs
  production never trades, the same construct at default settings, labelled as such), a coin at every rate,
  lowest-of-N turn, RSI.
- **What counts as a win:** the model's curves dominate production's (more true pivots caught at the same precision,
  or the same catches more precisely / earlier / closer to the low) in most walk-forward folds AND most calendar
  years (§4), and beat the coin.
- **After a win:** the strategy is designed around the model's outputs (expected hold, potential, pain) in a separate
  study; only then does any backtest (e.g. `scripts/campaign/run_windows.py`) enter the picture.

### 7. Integration path (only for a winner)

A pooled, pretrained model is outside today's per-stock `ExtremaModel` contract
(`reviews/extrema_model_research_inventory_20261018.md` §1: no save/load, every boot retrains). A winner needs:

- an adapter model type that loads a pretrained artefact and computes the lab's factors live;
- an offline (re)training job;
- a t2.micro inference budget check (torch is too heavy for the box, so export to ONNX or distil to trees);
- re-calibration of the thresholds.

That is a spec-first build in `to_develop/`, and only after a lab win.

### 8. Traps to design out from day one

- **Look-ahead:**
  - centred smoothing;
  - full-sample normalisation;
  - labels leaking into features;
  - higher-TF bars joined before they complete;
  - cross-stock leakage in pooled folds;
  - universe chosen by present-day lists.
- **Overlapping labels:** neighbouring bars share outcomes, so use uniqueness sample weights, purge and embargo.
- **Multiple testing:** log every arm × scheme in a lab ledger (`reviews/model_lab/LEDGER.md`, same style as the
  TD-018 ledger) before looking; report the number of arms tried with every "win".
- **Survivorship and hindsight:** see § Data.
- **Unit tests for leakage:**
  - every factor at bar *t* must be unchanged when bars after *t* are deleted;
  - every fold's training labels must end ≥ *H* bars before the test start.

## Phases

| Phase | Deliverable | Rough size |
|---|---|---|
| L0 | Lab store + fetcher (staged universe), factor library, target builders T1–T5, leakage unit tests | 2–3 days + fetch time |
| L1 | Split engine (all §4 schemes) + scoring report; baselines incl. production P(min) | 2 days |
| L2 | Pooled logistic + GBDT, all targets, 15m and day first, then the other TFs | 1–2 days + compute |
| L3 | Sequence models (torch/MPS), multi-task | 3 days + compute |
| L4 | Winner → adapter spec → Stage B → paper | only on a lab win |

## Start here (new session)

1. Read, in order:
   - this doc;
   - `reviews/extrema_campaign/CAMPAIGN_ROUND1_20261018.md`;
   - `reviews/extrema_campaign/LEDGER.md` (skim the EXP-20/22 and Stage B rows);
   - `reviews/extrema_model_research_inventory_20261018.md` §1–2.
2. Work on a branch `exp/model-lab` in its own worktree (`../trader-2-wt/model-lab`; symlink `config/.env`, `data`,
   `lab_data` from the main checkout, as the TD-018 worktrees did).
3. Code location: `research/model_lab/` (new package, no imports from `trader.strategies` or `trader.backtest`; only
   `trader.data`, `trader.auth`, `trader.core`). Python: `.venv/bin/python` (no bare `python`). Lab-only deps:
   `requirements-lab.txt`.
4. Kite: `.venv/bin/python scripts/kite_totp_refresh.py --no-restart` if the token is stale (pre-authorised).
5. Build L0 first, starting with the leakage tests. Write a lab ledger row per arm/scheme before running it. Commit and
   push after each phase; the full pytest suite must stay green (`.venv/bin/python -m pytest -q`; ISS-11 fails
   09:15–15:30 by design).
6. Report every result with weighted win % next to P&L (owner criterion), use the model/strategy terms above, and scope
   every negative result to the construct actually tested.
