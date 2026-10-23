# FVM — Implementation Plan

Build plan for the Fundamentally-Validated Momentum strategy. Companion to
`FVM_Strategy_Architecture.md` (what/why) and `FVM_Design_Decisions.md` (exact mechanisms +
data sourcing). This is the **how-to-build**, sequenced and milestone-gated.

## Guiding principles
1. **Validate before live (the central gate).** Build data → factors → backtest → *prove it beats
   naive momentum* BEFORE building any live integration. If the rules baseline fails the go-live
   bar (Design §12c), iterate or shelve — do **not** build the live system on an unvalidated edge.
2. **Rules-only v1.** No ML in the critical path. GBT challenger is a later, gated experiment.
3. **Respect the rate budget.** Excel Connect = 50 stocks/day, 500/month → ingestion is a rolling,
   event-driven fetcher, never a "pull everything daily" job.
4. **Reuse existing patterns.** Subclass the `Strategy` ABC, emit the existing `Signal` contract,
   reuse `costs.py`, the `Store`/SQLite layer, config patterns. Keep live/backtest parity (a core
   project value).
5. **Separate sleeve.** FVM runs as its own capital sleeve alongside LRExtrema — independent
   capital + risk limits; never starves the other.

## Net-new vs extends-existing
| Area | New modules | Extends |
|---|---|---|
| Data | `data/fundamentals.py` (PIT store), `data/ingest/{excel_connect,screener,nse}.py`, `data/universe.py` | `data/historical.py` (weekly, universe price), `data/store.py` (new tables) |
| Engine | `strategies/fvm/` pkg: `factors.py`, `scoring.py`, `technical.py`, `vetoes.py`, `fvm.py` (FVMStrategy) | `strategies/registry.py` |
| Backtest | `backtest/fvm_engine.py` (positional), `backtest/labels.py` (triple-barrier) | `costs.py` (reuse) |
| Risk | `risk/sleeve.py` (positional sizing/exits/caps) | `risk/manager.py` (sleeve routing) |
| Live | scheduler jobs, UI panels | `main.py`, `scheduler/jobs.py`, `ui/` |
| Scripts | `scripts/fvm_ingest.py`, `scripts/fvm_backtest.py`, `scripts/fvm_validate.py` | — |
| Config | `strategies.fvm` block, `sleeves` capital, per-sector/stock caps | `config/config.yaml` |

---

## Phase 0 — Data foundation  *(biggest, highest-risk; do first)*

**0.1 PIT vintaged fundamental store** (`data/fundamentals.py` + new SQLite tables)
- `fundamentals_raw(symbol, fiscal_period, statement, field, value, knowledge_date)` — append-only,
  vintaged. Read API returns "as-of date T" snapshots.
- `index_membership(symbol, date, in_universe)` — from NSE reconstitution back-application.
- `shareholding(symbol, quarter, promoter, fii, dii, pledge, holders, knowledge_date)`.
- `fundamental_scores(symbol, date, pillar1..5, composite, veto_flags, veto_reason)`.

**0.2 Ingestion adapters** (`data/ingest/`)
- `excel_connect.py` — pull fundamentals (P&L/BS/CF, consolidated, 10+ yr) into the PIT store.
  **SPIKE FIRST:** determine access method — (a) drive the Google Sheet via Apps Script / Sheets
  API and read cells, or (b) call the connector's underlying Trendlyne endpoint+token directly
  (cleaner if feasible). Rolling **50/day** scheduler; idempotent; respects 500/month.
- `screener.py` — historical shareholding (Pillar 4). Export-endpoint or parse; rate-limited;
  caching; the one ToS-gray surface — keep it isolated and replaceable.
- `nse.py` — index membership reconstitution, naive-momentum benchmark series, ASM/GSM lists.
- Price → extend `data/historical.py` for weekly resampling + universe-wide fetch via Kite.

**0.3 Universe builder** (`data/universe.py`)
- PIT Nifty-500 membership ∩ liquidity (Kite turnover floor) ∩ non-financial (AMFI exclusion).
- Announcement-date join for PIT knowledge-dates; **fallback = fixed ~45-day lag** if exact-date
  assembly is heavy.

**Deliverable:** queryable PIT store + a built universe for any historical date. **Risk:** Excel
Connect access method (spike), PIT correctness, delisted-name financials (survivorship-in-data —
accept currently-listed survivors for v1, flag inflation).

## Phase 1 — Fundamental engine  *(rules scoring)*
- `factors.py` — all 5 pillars per Design §2/Piece 2 (floored-YoY acceleration, OPM/consistency,
  PEG trailing-only, P/E-vs-history, EV/EBITDA gross-debt, CFO/NP, D/E, ROCE, FII/DII/promoter/
  pledge, sector-tailwind realized). Drop institutional-count (no source).
- `scoring.py` — winsorize(caps→1/99) → percentile (z for PEG) → sector-relative (AMFI coarsened
  ≥20/bucket) → pillar → composite. N/A drop-renormalize, missing→0.5. Daily rank recompute.
- `vetoes.py` — the 4 backtest vetoes (CFO, D/E+coverage, pledge, manufactured-earnings) +
  min-scoreability gate. (Compliance veto live-only.)
- **Tests:** hand-computed factor values on a few stocks; sign-convention (1.0=good) audit.

## Phase 2 — Technical layer
- `technical.py` — weekly 40w/10w MA + Trend_Score (multiplicative soft-gates); daily 50d MA, ATR,
  volume, base/breakout detection → Timing_Score (pullback×reversal, breakout×volume); parabolic
  extension veto; wide catastrophe initial stop. All from Kite price.

## Phase 3 — FVM strategy + signals
- `fvm.py` `FVMStrategy(Strategy)` — Gate A (composite pctile≥70 AND floor AND no veto AND
  min-scoreability) → Gate B (Trend_Score floor, hard) → event-driven trigger → rank =
  within-pool fundamental-pctile × Technical_Score. Emit `Signal` (reuse contract).
- Register in `registry.py`; add `strategies.fvm` config block.

## Phase 4 — Backtest engine  *(net-new, positional)*
- `backtest/fvm_engine.py` — separate from the intraday LRExtrema engine (different clock + inputs):
  weekly+daily streams, **PIT fundamental joins** (no lookahead), sleeve sizing (risk-based, wide
  stop), sector/stock caps, full exit stack (veto=Clock1, weekly-break=Clock2, valuation-exhaustion
  trim, two-stage trail, recycle), regime throttle, earnings enter-blackout. Reuse `costs.py`.
- `backtest/labels.py` — triple-barrier (vol-scaled) labeler over the eligible pool (for evaluation
  + future ML), purge/embargo aware.
- Metrics + benchmark comparison vs naive momentum + Nifty500 buy-hold.

---

## ⛔ MILESTONE A — VALIDATION GATE  *(decision point — do not skip)*
Run rolling, purged/embargoed walk-forward (Design §12a). Evaluate the **rules-only** baseline:
1. **Beats naive momentum** on net return (the thesis test, §12b) — *decisive*.
2. **Profitable in a majority of OOS folds** (§12c).
3. **Max drawdown within ceiling.**

- **PASS →** proceed to Phase 5 (live).
- **FAIL →** iterate factor formulas / thresholds within walk-forward, or invoke the deferred R1
  Plan-B (fundamentals-as-gate-only, momentum unfiltered), or **shelve**. **Build no live code until
  this passes** — this is the §6/§12 discipline made operational.

---

## Phase 5 — Live integration  *(only if Gate A passes)*
- Wire `FVMStrategy` into `main.py` as a second strategy on its **own sleeve** (config capital +
  caps); LRExtrema untouched.
- Live data: Excel Connect **event-driven** fundamental refresh (stocks that just reported), Kite
  price/ticks, NSE files (regime, ASM/GSM, benchmark). Daily rank recompute.
- `risk/sleeve.py` — positional sizing, exit stack, trims (wire entry→partial→remainder→final, no
  orphaned remainder — known LRExtrema scale-out gap to avoid), recycle, sleeve drawdown halt.
- `scheduler/jobs.py` — fundamental-refresh job (rate-budgeted), regime check, earnings-blackout
  calendar.
- UI panels: eligible pool, composite/pillar scores, veto reasons, open positions, exit clocks.
- **Paper-trade 2–4 weeks** before live capital (project norm).

## Phase 6 — ML challenger  *(deferred; gated)*
- GBT factor-combiner vs the rules baseline; ships only if it beats it on majority of
  purged/embargoed folds AND return delta ≥ 0 (Design §8c). Trains on the Phase-4 triple-barrier
  labels.

---

## Top implementation risks
1. **Excel Connect programmatic access** — Sheets-connector vs direct endpoint; rate limits.
   *Mitigate:* spike in Phase 0.1 before committing the ingestion design.
2. **PIT correctness** — announcement-date join / restatement. *Mitigate:* vintaged store + 45d-lag
   fallback; never overwrite.
3. **Delisted-name survivorship-in-data** — Screener lacks delisted financials. *Mitigate:* accept
   survivor universe for v1 + quantify inflation; premium archive later if needed.
4. **Backtest engine complexity** — positional + fundamentals + sleeve is substantial net-new code.
   *Mitigate:* build incrementally, test PIT joins hard, keep live/backtest parity from day one.
5. **The validation might fail (R1)** — that's the point of the gate; Plan-B deferred.

## Open implementation decisions (resolve at each phase)
- Excel Connect ingestion method (Apps Script/Sheets API vs reversed endpoint).
- Fundamental store schema (long/vintaged EAV vs wide-per-statement).
- Two-sleeve capital model in live config (fixed split; how `RiskManager` routes per sleeve).
- Whether `fvm_engine` shares any harness with the existing engine (likely fully separate).
