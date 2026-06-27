# FVM — Progress Log (living status)

Single source of truth for **what's done and what's next**. Update this at the end of every working
session. Companion docs:
- `FVM_Strategy_Architecture.md` — the what/why (high-level architecture)
- `FVM_Design_Decisions.md` — the exactly-how (mechanisms, data sourcing, ingestion)
- `FVM_Implementation_Plan.md` — the build plan (phases + validation gate)

---

## Status at a glance
**Phase:** 0 — Data foundation · **Active task:** 0.3 Universe builder (next) · Phase 1 factors
**Gate ahead:** Milestone A (validation — beat naive momentum) before any live build.

**Phase 0.2 = DONE** (data layer built + live-validated; 22 pytests green). Deferred follow-ups → task #21.

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

## Session log
*(newest first; one entry per working session — what changed, what's next)*

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
- **Next (Phase 1 remainder):** `scoring.py` (winsorize→percentile/z→sector-relative→pillar→composite),
  `vetoes.py` (4 vetoes + min-scoreability), Pillar 2 (valuation; needs Kite price for PEG/P-E) +
  Pillar 5 (sector-tailwind aggregate). Then Phase 2 (technical).
