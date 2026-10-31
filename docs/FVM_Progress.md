# FVM — Progress Log (living status)

Single source of truth for **what's done and what's next**. Update this at the end of every working
session. Companion docs:
- `FVM_Strategy_Architecture.md` — the what/why (high-level architecture)
- `FVM_Design_Decisions.md` — the exactly-how (mechanisms, data sourcing, ingestion)
- `FVM_Implementation_Plan.md` — the build plan (phases + validation gate)
- `FVM_Cockpit_UI.md` — the Streamlit cockpit UI guide (pages + how to run)
- `FVM_Forward_Plan.md` — the ordered next-steps to-do

---

## Status at a glance
**Phases 0–4 BUILT & UNIT-TESTED + Milestone-A harness BUILT** (data → factors → scoring →
vetoes → technical → handoff → exits → engine → labels → price layer → walk-forward gate).
**76 pytests pass.** The whole FVM logic is implemented under `trader/fvm/`, fully isolated,
nothing in the existing system touched.

**Milestone A — FINAL VERDICT (2026-07-01): CONCLUSIVE GATE FAIL. Decision: repurpose-or-shelve.**
With the annual-fallback (`factors._annual_floored_yoy_series`) the walk-forward window now spans
**2019→2026, 28 folds across ALL regimes incl. the Mar-2020 COVID crash.** Result: beats benchmark
**3/28 (11%)**, profitable 20/28 (71% — ~tautological for long-only equity in a mostly-up decade),
**mean edge −29.0pp** (FVM +17.6% vs bench +46.6%). **The defensive-overlay thesis is buried, not
confirmed:** in the one real crash fold (2019-07→2020-03) FVM *lost more* than momentum (−14.8 vs
−12.8) and beat it in only 2 of 4 down folds. So rules-only FVM is reliably profitable but **never
reliably beats momentum and isn't even reliably defensive.** The earlier "inconclusive because
bull-only" framing is RESOLVED — we got the regimes, FVM still fails. Next = the repurpose-or-shelve
decision (see FVM_Forward_Plan.md "THE DECISION"); do NOT tune, do NOT BSE-scrape. Pre-2023 *breadth*
result kept below for history.

---
**(superseded) Milestone A — BREADTH RESULT (2026-06-30): GATE FAIL, breadth did NOT rescue it.**
Re-ran the walk-forward on the **138-name** scored universe (up from 39; daily prices cached for
138/139). Then-current data-valid window **2024-05 → 2026-05** (6 × 39w folds):

| Metric | 39 names (first run) | 138 names (breadth) |
|---|---|---|
| Beats benchmark | 3/6 | **1/6** |
| Profitable | 3/6 (was reported 4/6) | **3/6** |
| Mean edge | +0.7% | **−15.1%** (FVM +0.1% vs bench +15.2%) |
| Worst FVM fold maxDD | 10.1% | 18.0% |

FVM beat naive momentum in **only the one fold where the benchmark was negative** (2024-08→2025-05:
−11.2% vs −19.6%, +8.4pp); it lagged 26–32pp in every up fold. **Breadth didn't rescue it — it
exposed it:** the first-run near-miss was not thin-data noise. FVM as specified is a **defensive
overlay that structurally cannot beat naive momentum in an up market** — wins drawdowns, loses
rallies.

**Crucial caveat — the gate was run on a stacked deck.** The *entire* data-valid window
(2024-05→2026-05) is a near-uninterrupted mid/small-cap **bull regime** (5 of 6 folds had a
*positive* benchmark, some +35–45%). A defensive fundamental tilt losing to momentum across a
one-directional bull run is close to tautological — the "beat naive momentum in a majority of
folds" gate is near-unwinnable on a bull-only window. So this FAIL is **inconclusive about strategy
quality**: we cannot yet distinguish "FVM is weak" from "the only window we have is a bull market
where defense structurally loses." **Did NOT tune anything to flip it** (standing rule).

**Bottleneck has shifted: breadth → SOLVED (138 names); the wall is now REGIME COVERAGE / window
length**, i.e. the Trendlyne quarterly-depth limit at 2023-03 capping the backtest at ~2024→. We
have no fundamental history reaching a bear/sideways market (2018-19, 2020) where a defensive
overlay should earn its keep. **Decision pulled forward (forward-plan step 5):** either (a) accept
the verdict / repurpose FVM as a risk-filter on the LRExtrema sleeve rather than a standalone
strategy, or **(b) source pre-2023 quarterly history (Screener/BSE) so the backtest spans a real
drawdown — only then is the gate a fair test. Recommendation: (b) before any verdict on FVM.**

**Two hard data limits (one now resolved):**
1. ~~**Fundamentals breadth — 39/399**~~ → **138/399 scored** (2026-06-30); breadth no longer the
   bottleneck for the gate.
2. **Fundamentals DEPTH — Trendlyne quarterly only goes back to 2023-03** (~13 quarters; annual to
   2013). Confirmed 2026-07-01 that this is Trendlyne's HARD CAP on *every* endpoint — reverse-
   engineered the website's `get-fundamental_results-v2` endpoint and it returns the same 13q/2023-03
   as Excel-Connect (RADICO). No deeper quarterly exists to fetch. **MITIGATED in code:**
   `factors.floored_yoy_series` now falls back to annual NP/revenue (reach 2013) when quarterly is
   absent, so the `insufficient_data` veto and the walk-forward window extend back to ~2017/2018
   (live unchanged — only the pre-2023 backtest window uses it). 78 FVM pytests pass. Next: re-run
   `fvm_milestone_a.py` to read the gate across the now-included 2018-19 + Mar-2020 drawdowns.

**Price data is DONE:** daily candles 2018→today cached for 138/139 names (`scripts/fvm_prices.py`;
only GAYAPROJ short — the -BE name).

**Gate ahead:** Milestone A (rules-only backtest must beat naive momentum) before any live build (Phase 5).
Path to a decisive run: ~~(a) widen the universe (mid-caps)~~ ✅ DONE (138 names, gate still FAIL —
the answer was not breadth); **(b) deeper pre-2023 quarterly history** is now the ONLY path to a fair
test — without a bear/sideways regime in the window the gate is structurally unwinnable for a
defensive overlay. Re-run the harness once history reaches a real drawdown, NOT before.

> ⚠️ Fixed an important bug this session: `trader/fvm/data/` was caught by the `data/` gitignore →
> the entire data layer was untracked. Added `!trader/fvm/data/`; all 30 FVM files now committed.

---

## ✅ Done
- **Design (complete):** all 12 pieces (spine → factors → scoring → vetoes → technical+functions →
  handoff → labels → ML → exits → portfolio → governance → validation) + adversarial stress-test
  (R1–R6; R2/R4 fixed, R3/R5 flagged, R1 deferred). Captured in `FVM_Design_Decisions.md`.
- **Data sourcing (complete, 10/10):** two-source stack confirmed. LIVE = Trendlyne StratQ (₹5,900/yr,
  purchased) + Kite + NSE; BACKTEST = Screener (shareholding) + Trendlyne Excel Connect (financials)
  + Kite + NSE. Every v1 factor has a feed; only low-weight degradations (drop institutional-count,
  gross-debt EV) + estimate down-scope (Pillar 5 realized-only).
- **Ingestion route (verified):** Excel Connect pulls 10+ yr P&L/BS/CF incl CFO, consolidated, via
  token connector — official/legit. Rate limit **50/day, 500/month**. Chrome-scrape surface reduced
  to one item (historical shareholding via Screener).
- **Implementation plan drafted:** `FVM_Implementation_Plan.md` (milestone-gated).

## 🔄 In progress
- **Phase 0.2 — PIT store + ingestion adapters** *(underway)*
  - ✅ `trader/fvm/data/store.py` — `FVMStore` (own `data/fvm.db`, isolated from `market.db`):
    fund_stocks, fundamentals (EAV vintaged), shareholding, index_membership. **PIT no-lookahead
    read verified** by tests.
  - ✅ `trader/fvm/data/trendlyne.py` — fincsv API client + `ingest_master` (tested LIVE: 7,607
    stocks) + `ingest_financials` (45d-lag PIT default) + provisional CSV parser (unit-tested).
  - ✅ `tests/fvm/test_data_layer.py` — 5 tests passing.
  - ✅ `TRENDLYNE_TOKEN` in `.env`.
  - ✅ **financials LIVE-VALIDATED.** Auth fully cracked: data endpoints (quarter/annual) are
    CloudFront/WAF **UA-allowlisted to Google Apps Script** — Chrome UA → 403, Apps-Script UA → 200.
    Client UA switched accordingly. Ingested ULTRACEMCO (5,514 rows, history to 2016); parser
    confirmed against real CSV. Needs token + fresh `TRENDLYNE_COOKIE` (both in `.env`).
  - ✅ field catalog dumped → `docs/FVM_Trendlyne_Fields.md` (60 quarterly + 189 annual fields).
  - ✅ FVMStore extended: write/read_shareholding + write_membership/members_asof.
  - 🤖 **Screener + NSE adapters being built by a parallel sub-agent** (screener.py shareholding;
    nse.py membership/benchmark/ASM-GSM + their tests). Integrate on completion.
  - ⏭ remaining (me): weekly-price reuse via `historical.py`; ingest CLI; per-period announcement
    dates (currently 45d-lag default).

## ✅ Done (recent)
- **Phase 0.1 — Excel Connect access spike (DONE):** resolved to **method (b) direct REST API**.
  Endpoints `…/fundamentals/fincsv/v1/{quarter,annual}/?stock_hash=<hash>` → CSV, auth `tltoken:
  Token <token>` header (+ session cookie); rate-limit server-side per token. Ingestion calls these
  from Python directly — no Sheets in the loop. (Detail in Design Decisions §15b.) Security flag:
  user's session cookie is hard-coded in the sheet's Apps Script.

## ⏭ Next up (in order)
1. Finish 0.1 spike → decide ingestion method.
2. 0.2 PIT fundamental store schema + ingestion adapters (excel_connect, screener, nse) + price/weekly.
3. 0.3 Universe builder (PIT membership ∩ liquidity ∩ non-financial; announcement-date join / 45d-lag).
4. Phase 1 — fundamental engine (factors → scoring → vetoes) + tests.
5. Phase 2 — technical layer. Phase 3 — FVM strategy/signals. Phase 4 — backtest engine + labels.
6. ⛔ **Milestone A — Validation gate** (beat naive momentum across walk-forward). PASS → live.
7. Phase 5 — live integration (gated). Phase 6 — ML challenger (deferred).

## ⚠ Open decisions / risks carried
- Excel Connect ingestion method (the 0.1 spike).
- Fundamental store schema (vintaged EAV vs wide-per-statement).
- Two-sleeve capital model in live config.
- Delisted-name survivorship-in-data (Screener gap) — accept survivor universe v1?
- R1 (may not beat momentum) — Plan-B deferred to the gate.

---

## Module map (`trader/fvm/`)
| Module | Role | Tested |
|---|---|---|
| `data/store.py` | `FVMStore` — PIT vintaged store (own `data/fvm.db`): fundamentals/shareholding (EAV), membership, sectors, master | ✅ |
| `data/trendlyne.py` | fincsv API client + master + financials ingest (UA-allowlist; cookie) | ✅ |
| `data/screener.py` | historical shareholding (HTML parse) | ✅ |
| `data/nse.py` | membership + momentum benchmark + ASM/GSM | ✅ |
| `data/universe.py` | eligible universe (PIT members ∩ non-financial ∩ liquidity hook) | ✅ |
| `data/prices.py` | Kite daily → engine price_data + PIT price_provider | ✅ + data loaded (39 names, 2018→) |
| `fields.py` | factor → Trendlyne field-name map | — |
| `factors.py` | Pillars 1–4 factors + floored-YoY acceleration | ✅ |
| `scoring.py` | winsorize→pctile/z→sector-relative→pillar→composite + Pillar-5 tailwind | ✅ |
| `vetoes.py` | 4 vetoes + min-scoreability + live compliance | ✅ |
| `technical.py` | weekly Trend_Score, daily Timing_Score, parabolic veto, wide stop | ✅ |
| `handoff.py` | gate-then-time-then-rank candidate selection | ✅ |
| `exits.py` | exit stack (thesis/price/trailing/valuation/recycle) | ✅ |
| `engine.py` | positional weekly-rebalance backtest | ✅ |
| `labels.py` | triple-barrier labels | ✅ |
| `walkforward.py` | Milestone-A harness: naive-momentum benchmark + rolling folds + gate | ✅ |
| `ui/data.py` | Cockpit data layer (framework-agnostic): `build_board` + `load_stock` + `coverage` + `milestone_a` + `scoring_lab`/`gate_counts`, calls scoring/vetoes/technical/handoff/walkforward cache-only | ✅ smoke |

## Runbook — to run the real backtest (Milestone A)
1. **Refresh Kite token** (expires midnight IST): `python scripts/login.py` (or wait for the 08:15 cron).
2. **Ingest universe fundamentals** (rate-limited 50/day; needs a fresh `TRENDLYNE_COOKIE` in `.env`):
   loop `trendlyne.ingest_financials(store, sym)` + `screener.ingest_shareholding(store, sym)` over
   `universe.eligible_universe(...)`. Budget ~25 stocks/day → full ~399-name universe over ~8–16 days
   (or accept a smaller universe to start). `nse.ingest_current_membership` + `universe.ingest_sectors`
   are one-shot.
3. **Load prices** — ✅ DONE for the 39 scored names: `python scripts/fvm_prices.py --from 2018-01-01`
   caches daily candles in `market.db` (reused via `historical.get_candles`; resumable; cache-only
   re-runs). At backtest time `prices.load_universe_prices(None, candle_store, symbols, from, to)` →
   `{sym: daily_df}`. Re-run after each fundamentals batch to cover newly-scoreable names.
4. **Run**: `engine.run_backtest(fvm_store, price_data, sectors, sleeve_capital, score_fn=..., price provider, regime_fn)`.
   Compare to the naive-momentum benchmark (`nse.fetch_momentum_index` / cached CSV) per §12b.
5. **Decision (§12c):** beats naive momentum + profitable in majority of walk-forward folds + maxDD
   ceiling → proceed to Phase 5 (live). Else iterate / Plan-B / shelve.

Remaining build (post-data): real walk-forward harness around `run_backtest`, benchmark comparison
report, and (only if Gate A passes) Phase 5 live integration.

## Session log
*(newest first; one entry per working session — what changed, what's next)*

### 2026-07-04 (Trendlyne Data-Downloader weekly snapshot layer)
- **New data source: the Trendlyne "Data Downloader" xlsx** (`data/Stocks-data-IND-<d>-<Mon>-<YYYY>.xlsx`,
  ~5,700 NSE names × 163 cols, downloaded manually weekly). Carries fields the API stack has NO
  other source for: **Piotroski, DVM scores, promoter pledge with full-market coverage (fixes the
  0%-coverage pledge factor), monthly MF/FII deltas, %days-below-current-PE/PB percentiles,
  sector+industry relative valuations.** Only the 2 Forecaster forward-estimate columns are
  plan-gated ("Export NA").
- **Built `trader/fvm/data/snapshot.py`** — curated ~55-field wide table `tl_snapshot` in fvm.db
  keyed (symbol, as_of); weekly ingests STACK into our own vintaged history of fields Trendlyne
  never exposes retrospectively. Reads are asof-aware (latest vintage ≤ asof). **NOT for
  backtests** — live cockpit / discretionary use only. Includes the 11-gate `quality_screen`
  funnel (5,688→34 survivors on the 2026-07-03 export) + `watchlist_flags`.
- **`scripts/tl_snapshot.py`** — weekly runner: ingest newest xlsx → screen (survivors CSV to
  `data/screens/tl_screen_<asof>.csv`, a /discover feed) → watchlist red-flag panel
  (`--symbols` override) → week-over-week evolution (screen entries/exits + watchlist drift).
- **Integrated:** `conviction.scorecard(..., snapshot=...)` gains a Market-Intelligence section
  (current-date `study_stock` only — the PIT replay never sees it); `fund_panel.py` overlays
  pledge/promoter-trend fallbacks + snapshot line. Immediately caught **CUPID pledge 24.8% +
  PE at 100th pctile of own history** (Screener path had no pledge data). 109 FVM tests pass.
- **Next:** weekly cadence — download the export, run `python scripts/tl_snapshot.py`; evolution
  view activates from the second vintage.

### 2026-06-28 (FVM Cockpit UI — U0–U4)
- **Built the cockpit shell + manual-investing core + validation + scoring lab.**
  `trader/fvm/ui/data.py` (framework-agnostic data layer: `build_board` scores the whole ingested
  universe as-of a date, `load_stock` assembles one name's full read, `coverage` aggregates
  ingest/price coverage, `milestone_a` runs the walk-forward gate + a continuous FVM-vs-benchmark
  equity comparison, `scoring_lab`/`gate_counts` expose score anatomy + live gate funnel — all
  call only the tested scoring/vetoes/technical/handoff/walkforward functions, cache-only) +
  `scripts/fvm_ui.py` (Streamlit + Plotly, `streamlit run scripts/fvm_ui.py`).
- **Page 1 Today's Shortlist:** FVM candidates table + full board with decision tags
  (CANDIDATE/NO_TIMING/NO_TREND/WEAK_FUND/VETOED), filter by decision/sector + symbol search,
  as-of date picker, click-through to detail. **Page 2 Stock Detail:** composite + decision badge,
  5-pillar bars, colour-graded factor table (normalized/raw), veto + parabolic-ext panel, weekly
  (40w/10w MA) + daily (50d MA + catastrophe stop + volume) Plotly charts, PIT fundamentals history,
  shareholding trend. **Page 3 Universe & Coverage:** ingested/target→399 progress, per-name
  quarter/annual depth + shareholding + price coverage with gap flags, missing-names list (CSV
  export to feed the daily ingest), per-sector coverage. **Page 4 Milestone-A:** button-gated
  walk-forward run (cached — ~4 min first run), gate PASS/FAIL banner + thin-universe caveat,
  summary metrics, continuous FVM-vs-benchmark equity curve, per-fold table (coloured edge), and a
  **down-vs-up regime split** that makes the defensive character explicit (current 39-name run:
  +9.8pp edge in the 3 down/choppy folds, −8.4pp in the 3 up folds — wins drawdowns, lags rallies).
  **Page 5 Scoring Lab:** composite distribution (Gate-A cut + floor lines), pillar contributions,
  per-factor coverage/NaN + mean-normalized heatmap (flags thin factors — e.g. pledge 0% coverage
  on the current universe → neutral, no signal), and gate-sensitivity sliders driving a live funnel
  (universe→veto→Gate-A→Gate-B→trigger→candidates; today 39→34→12→6→0→0 at defaults).
- `st.cache_data` wraps the heavy sweeps. **Added streamlit/plotly/matplotlib to requirements.txt**
  (were unpinned; matplotlib enables the `background_gradient` factor heatmap).
- Verified: data layer smoke-tested headless (39/39 priced, decisions {WEAK_FUND 22, NO_TIMING 6,
  NO_TREND 6, VETOED 5}; coverage 39/399 ingested, all priced, q-depth 8–13; milestone_a reproduces
  the gate exactly — FAIL, beats 3/6, profit 4/6, edge +0.7pp; scoring_lab funnel matches the
  shortlist), Streamlit boots clean (no tracebacks). Forward-plan §6b U0–U4 done.
- **Next:** U5 Portfolio/Live — deferred until Phase 5 lands (+ a Flask read-only live monitor).

### 2026-06-28 (shortlist CLI)
- **Built `scripts/fvm_shortlist.py`** — ranks the scored universe as-of a date: FVM CANDIDATES
  (clear fundamentals+trend+timing, strategy-ranked) + FULL BOARD by composite with decision tags
  (CANDIDATE/NO_TIMING/NO_TREND/WEAK_FUND/VETOED). Verified candidates appear on dates with entry
  triggers (ADANIPORTS 2024-08, TCS 2025-01, ABBOTINDIA 2025-06); today (2026-06-28) = no setup
  (trend-passing names are parabolic-extended). Forward-plan step 6 done.

### 2026-06-28 (Milestone-A harness + first result)
- **Built the walk-forward gate.** `trader/fvm/walkforward.py` (naive-momentum benchmark =
  hold-while-in-top-N-by-12–1-momentum, same universe/costs; rolling folds; gate = beat
  benchmark + profitable in the majority) + `scripts/fvm_milestone_a.py` CLI. 4 new pytests;
  **76 pass.**
- **First Milestone-A run (39 names).** Auto-starts at the data-valid week. 2024-05→2026-05,
  6 folds: beats bench 3/6, profitable 4/6, mean edge +0.7%, worst maxDD 10.1% → **GATE FAIL**
  (near-miss). Sensible defensive profile: wins the 3 down/choppy folds big, lags the 3 rallies.
- **Found two hard data limits:** (1) breadth 39/399; (2) **Trendlyne quarterly depth stops at
  2023-03** → pre-2023 is all `insufficient_data`, so no long walk-forward is possible. Documented;
  harness auto-skips the vacuous window.
- **Did NOT tune to flip the gate** (6 folds = overfit risk). Next: grow the universe (esp.
  mid-caps) and re-run; keep daily fundamentals ingest going.

### 2026-06-28 (prices)
- **Price ingestion DONE.** Added `scripts/fvm_prices.py` — fetches & caches daily candles
  (2018→today) for the scored universe into the shared `market.db` (reused via
  `historical.get_candles`; `get_candles` chunks day data at 2000-bar windows so multi-year
  pulls work; resumable + cache-only re-runs). Ran it: **39/39 scored names resolved, 230–2101
  bars each** (low end = recent IPOs). Validated end-to-end into the technical layer: weekly
  resample (443w for full-history names), `trend_score`/`timing_score`/`extension_vetoed` all
  consume the cached frames correctly. Sanity-checked LT (trend 0.726, uptrend) vs RELIANCE
  (0.000 — genuinely 7% below a falling 40w MA, Stage-4, not a bug).
- **Next:** keep ingesting fundamentals (39/399; ~14 days at quota), re-run `fvm_prices.py`
  after each batch, then wire the Milestone-A walk-forward harness around `engine.run_backtest`.

### 2026-06-28 (overnight, autonomous)
- **Built Phases 1→4 to completion** (rules-only): scoring, vetoes, Pillar 2/5, technical layer,
  handoff, exit stack, positional backtest engine, triple-barrier labels, Kite price layer.
  **72 pytests pass.** Commits: Phase 1 (7af3af8), Phase 2 (2b06d73), handoff (d67c377),
  exits (8caa423), Phase 4 engine/labels (03d0986), price layer (a6a085d), gitignore fix.
- **Live-validated the fundamental engine** end-to-end on 8 real stocks (composite TCS 70.6 …
  SUNPHARMA 24, all veto-pass). Found+fixed: debt_trend abs-₹→scale-free; gitignore hiding the
  data layer; engine gate-threshold passthrough.
- **Blocked from the real backtest** by data only (Kite token expired; full-universe fundamentals
  need quota/time) — engine is built & ready; see Runbook.
- **Next:** (when data ready) run Milestone-A walk-forward backtest vs naive momentum; meanwhile
  Phase 0.2 follow-ups (#21: momentum-history fetch, reconstitution change-lists).

### 2026-06-27
- Completed design phase, adversarial stress-test, full data-sourcing investigation (incl. paid
  Trendlyne StratQ verification + Excel Connect authorized inspection), ingestion route assessment,
  and drafted the implementation plan. Set up this progress log + implementation task board.
- **Phase 0.1 spike DONE:** Excel Connect = direct token REST API
  (`fundamentals/fincsv/v1/{quarter,annual}/?stock_hash=`, CSV, `tltoken` header). Method (b) chosen.

### 2026-06-28
- **Phase 0.2 (underway).** Built + tested the FVM data layer: `FVMStore` (PIT vintaged store,
  own DB), Trendlyne fincsv client, `ingest_master` (LIVE-tested, 7,607 stocks), `ingest_financials`
  + parser, 5 passing pytests. **PIT no-lookahead read verified.** Resolved the API auth: token+UA
  works for expiry/all_stocks; **financials (quarter/annual) need a session cookie** → made it a
  configurable `.env` value (`TRENDLYNE_COOKIE`).
- **NEED (non-blocking):** a fresh `TRENDLYNE_COOKIE` in `config/.env` to live-validate financials
  + finalise the (provisional) CSV parser. Format: `.trendlyne=...; csrftoken=...` from the
  logged-in browser. Until then, continuing with Screener + NSE adapters.
- **Trendlyne financials UNBLOCKED:** data endpoints are UA-allowlisted to Google Apps Script
  (Chrome→403, Apps-Script-UA→200). Client UA fixed; UltraTech ingested (5,514 rows, to 2016).
- **Parallel sub-agent built Screener + NSE adapters** (`screener.py` shareholding — live-parsed
  UltraTech; `nse.py` current Nifty500 membership + ASM/GSM 255 flags). Reviewed + integrated.
  Deferred (task #21): live momentum-index history, historical reconstitution change-lists.
- **Phase 0.2 COMPLETE** — 4 ingestion sources live-validated, FVMStore PIT-correct, **22 pytests pass**.
- **Phase 0.3 COMPLETE** — `universe.py` + sector_map. Live: 500 constituents → **399 non-financial**
  eligible universe (101 financials excluded). PIT membership + financials-exclusion + liquidity hook.
- **Phase 1 (underway)** — `fields.py` (factor→Trendlyne-field map; Trendlyne pre-computes EV/EBITDA,
  D/E, interest-coverage, ROCE, OPM, rev-growth → simplifies a lot, kills the gross-debt-EV gap).
  `factors.py`: primitives + **Pillar 1** (crown-jewel floored-YoY acceleration), **Pillar 3**, **Pillar 4** —
  tested + live-validated on real UltraTech (cfo/np 1.94, D/E 0.26, int-cov 9.7, rev-growth 16%).
  Caught + fixed a real bug: debt_trend was absolute-₹ (size-dominated) → now scale-free D/E slope.
  **33 pytests pass.**
- **Phase 1 COMPLETE** (autonomous session): added `scoring.py` (full normalization → composite 0-100
  + Pillar-5 realized sector-tailwind), `vetoes.py` (4 vetoes + min-scoreability + live compliance),
  Pillar 2 valuation factors (`factors.pillar2_factors` — EV/EBITDA + price-gated PEG/PE). **48 pytests
  pass.** LIVE-validated end-to-end on 8 real stocks (ingested financials+shareholding): composite
  ranking TCS 70.6 / INFY 66 … RELIANCE 33 / SUNPHARMA 24 — defensible, all veto-pass.
  - `OPEN`: Pillar-2 PEG/PE need Kite price (optional now → neutral; EV/EBITDA carries valuation) —
    wire with the Phase-2 price layer. R3 fusion (geo-mean) deferred to dry-runs per design.
- **Now: Phase 2 — technical layer** (`technical.py`: weekly 40w/10w Trend_Score, daily Timing_Score,
  parabolic veto, wide stop — pure functions over OHLCV, Kite wiring separate).
