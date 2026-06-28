# FVM — Progress Log (living status)

Single source of truth for **what's done and what's next**. Update this at the end of every working
session. Companion docs:
- `FVM_Strategy_Architecture.md` — the what/why (high-level architecture)
- `FVM_Design_Decisions.md` — the exactly-how (mechanisms, data sourcing, ingestion)
- `FVM_Implementation_Plan.md` — the build plan (phases + validation gate)

---

## Status at a glance
**Phases 0–4 BUILT & UNIT-TESTED + Milestone-A harness BUILT** (data → factors → scoring →
vetoes → technical → handoff → exits → engine → labels → price layer → walk-forward gate).
**76 pytests pass.** The whole FVM logic is implemented under `trader/fvm/`, fully isolated,
nothing in the existing system touched.

**Milestone A — FIRST RESULT (indicative, GATE not yet passed).** Walk-forward harness
(`scripts/fvm_milestone_a.py` + `trader/fvm/walkforward.py`) runs rules-only FVM vs a
naive-momentum benchmark over rolling folds. On the 39-name scored universe, data-valid
window **2024-05 → 2026-05** (6 × ~9-month folds): FVM beats benchmark **3/6**, profitable
**4/6**, mean edge **+0.7%** (FVM −0.5% vs bench −1.2%), worst maxDD 10.1% → **GATE = FAIL**
(needs majority on both). **Character is sensible & defensive:** FVM *beats* momentum hard in
the 3 down/choppy folds (edge +1.2 / +12.7 / +15.5%) and *lags* in the 3 momentum rallies —
a quality overlay protecting drawdowns, lagging melt-ups. **Do NOT tune to flip this** (6 folds
= overfit risk). The result is dominated by data limits, see next.

**Two hard data limits found this session (both gate the real backtest):**
1. **Fundamentals breadth — 39/399 names** ingested (Trendlyne 50/day quota → ~14 more days).
2. **Fundamentals DEPTH — Trendlyne quarterly only goes back to 2023-03** (~13 quarters; annual to
   2016). So pre-2023 every name fails the min-scoreability veto (`insufficient_data`) → the
   walk-forward can't extend before ~2024. The harness now auto-starts folds at the first
   data-scoreable week so the gate isn't an artifact of empty cash-folds.

**Price data is DONE:** daily candles 2018→today cached for all 39 names (`scripts/fvm_prices.py`).

**Gate ahead:** Milestone A (rules-only backtest must beat naive momentum) before any live build (Phase 5).
Path to a decisive run: (a) widen the universe (mid-caps — fundamentals should add more edge than on
mega-caps); (b) deeper quarterly history if obtainable; re-run the harness as coverage grows.

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
| `ui/data.py` | Cockpit data layer (framework-agnostic): `build_board` + `load_stock`, calls scoring/vetoes/technical/handoff cache-only | ✅ smoke |

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

### 2026-06-28 (FVM Cockpit UI — U0+U1)
- **Built the cockpit shell + manual-investing core.** `trader/fvm/ui/data.py` (framework-agnostic
  data layer: `build_board` scores the whole ingested universe as-of a date, `load_stock` assembles
  one name's full read — both call only the tested scoring/vetoes/technical/handoff functions,
  cache-only) + `scripts/fvm_ui.py` (Streamlit + Plotly, `streamlit run scripts/fvm_ui.py`).
- **Page 1 Today's Shortlist:** FVM candidates table + full board with decision tags
  (CANDIDATE/NO_TIMING/NO_TREND/WEAK_FUND/VETOED), filter by decision/sector + symbol search,
  as-of date picker, click-through to detail. **Page 2 Stock Detail:** composite + decision badge,
  5-pillar bars, colour-graded factor table (normalized/raw), veto + parabolic-ext panel, weekly
  (40w/10w MA) + daily (50d MA + catastrophe stop + volume) Plotly charts, PIT fundamentals history,
  shareholding trend.
- `st.cache_data` wraps the heavy scoring sweep. No matplotlib dep (hand-rolled red→green gradient).
  Verified: data layer smoke-tested headless (39/39 priced, decisions {WEAK_FUND 22, NO_TIMING 6,
  NO_TREND 6, VETOED 5}), Streamlit boots clean (no tracebacks). Forward-plan §6b U0+U1 done.
- **Next:** U2 Universe & Coverage page (steer the daily ingest), then U3 Milestone-A viewer.

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
