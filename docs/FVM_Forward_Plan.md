# FVM — Forward Plan (next steps, persists across sessions)

**Read this first on resume.** Companion to `FVM_Progress.md` (status log). This file is the
ordered to-do; `FVM_Progress.md` is what's already done. Last updated 2026-06-28.

## Where we are
- Strategy + harness fully BUILT & tested (76 pytests). Phases 0–4 + Milestone-A walk-forward.
- **Milestone A: GATE FAIL (near-miss)** on a thin 39-name / 2024-05→2026-05 window — beats
  benchmark 3/6, profitable 4/6, mean edge +0.7pp (both strategies ~flat). Defensive-overlay
  character (wins down/choppy folds, lags rallies). Result is **dominated by data limits**, not
  strategy quality — so the next steps are all about DATA, not tuning.
- Two hard data limits: breadth (39/399 names) and Trendlyne quarterly depth stops at 2023-03.

## The plan (ordered — top of the list is the critical path)

### 1. Re-order the ingest to prioritise MID-CAPS  ← DO THIS FIRST (tomorrow)
The store is skewed to large-caps (hand-ingested), the *worst* universe for a fundamental
overlay. Mid-caps are where quality/momentum divergence — and the edge, if real — is largest.
Change the ingest ordering in `scripts/fvm_ingest.py` so the daily quota fills mid-caps first
(e.g. sort the eligible universe by an inverse-size / index-rank proxy, or seed from a mid-cap
index membership). Cheap change, high leverage on what the next ~14 days of quota buy.

### 2. Run the daily fundamentals ingest until the universe fills
- `python scripts/fvm_ingest.py` after each Trendlyne quota reset (~25 stocks/day, resumable).
- Needs a fresh `TRENDLYNE_COOKIE` in `config/.env` if financials 403.
- ~14 days to the full ~399-name universe.

### 3. Re-run the price cache after each batch
- `python scripts/fvm_prices.py` (cache-only is cheap; only fetches newly-scoreable names).

### 4. Re-run the Milestone-A gate as coverage grows
- `python scripts/fvm_milestone_a.py` at ~150 names and again at full universe.
- Watch whether the defensive edge holds/strengthens with breadth.
- **NO parameter tuning** until the universe is broad — 6 overlapping folds is overfit territory.

### 5. Decide on the quarterly-depth limit (when we reach the gate)
Quarterly fincsv stops at 2023-03 → backtest can't extend before ~2024. Either (a) accept a
short-but-broad 2024→ window as the verdict (preferred — breadth > depth for power here), or
(b) source deeper quarterly history (Screener / BSE archives).

### 6. Manual-investing shortlist CLI  ✅ DONE (2026-06-28)
`scripts/fvm_shortlist.py` — runs scoring + vetoes + technical as-of a date over the ingested
universe and prints (1) FVM CANDIDATES (names clearing fundamentals+trend+timing, ranked as the
strategy ranks) and (2) FULL BOARD by composite with a per-name decision tag
(CANDIDATE / NO_TIMING / NO_TREND / WEAK_FUND / VETOED). `--asof`, `--top`, `--verbose`.
Usable now on the 39 names; gets meaningful as the universe fills (steps 1–3).

### 6b. FVM Cockpit UI  (U0+U1+U2 DONE 2026-06-28 — U3+ pending)
A UI on top of everything. **Stack decision: Streamlit + Plotly now** (reuse `scripts/ui.py`
pattern — research/manual-investing cockpit), **add a Flask read-only live-monitor later** when
Phase 5 lands (mirrors `trader/ui/`). **Build order: manual-investing core first** (U0 scaffold +
U1), rest follows.

**Hard rule:** UI never reimplements engine logic — it calls the tested `scoring` / `vetoes` /
`technical` / `handoff` / `walkforward` functions. Isolated under `scripts/fvm_ui.py` +
`trader/fvm/ui/`; reads `fvm.db` + `market.db` cache-only; never touches the LRExtrema UI or live
path. Use `st.cache_data` for the heavy per-day universe scoring sweep.

Page map (= "covers everything"):
1. **Today's Shortlist** (home) ✅ — interactive `fvm_shortlist`: candidates + full board, decision
   tags (CANDIDATE/NO_TIMING/NO_TREND/WEAK_FUND/VETOED), filter by decision/sector + symbol search,
   `asof` date picker, click-through to Stock Detail.
2. **Stock Detail** (drill-down, explainability) ✅ — composite + decision badge; 5-pillar bars +
   factor table (direction/normalized/raw, colour-graded); veto panel + parabolic-ext warning;
   technical charts (weekly candles + 40w/10w MA; daily + 50d MA + catastrophe stop + volume);
   fundamentals history (rev/NP/CFO/EPS/D-E/ROCE, PIT-vintaged); shareholding trend
   (promoter/FII/DII/pledge).
3. **Universe & Coverage** (ops) ✅ — ingested/target (→399) progress, per-name quarter/annual
   depth + shareholding + price coverage, gap flags, missing-names list (CSV export to feed the
   daily ingest), per-sector coverage.
4. **Milestone-A / Validation** — per-fold table, FVM vs benchmark equity curves, gate verdict,
   down-vs-up regime split, drawdown.
5. **Scoring Lab** — composite distribution, pillar contributions, sector tailwind, factor
   coverage/NaN rates, gate-sensitivity sliders (pctile_cut, trend_floor) → live candidate count.
6. **Portfolio / Live** — open positions, sleeve capital, exit-stack state (placeholder until Phase 5).

Build phasing: ~~**U0** scaffold + cached scoring-sweep helper~~ ✅ → ~~**U1** Shortlist + Stock
Detail~~ ✅ (`scripts/fvm_ui.py` + `trader/fvm/ui/data.py`, `streamlit run scripts/fvm_ui.py`) →
~~**U2** Coverage~~ ✅ → **U3** Milestone-A viewer (next) → **U4** Scoring Lab → **U5** Portfolio/Live
(+ Flask live monitor, after Phase 5).

### 7. (Gated on Milestone A passing) Phase 5 — live integration
Two-sleeve capital model, wire FVM signals into the live loop. Only after the gate passes on a
broad universe.

### 8. (Deferred) Phase 6 — ML challenger
Stays deferred; treat skeptically (see the meta-labeling lesson — it *worsened* outcomes before).

## Standing reminders
- Update `FVM_Progress.md` (session log) and this file at the end of each working session.
- Do not tune to flip the 6-fold gate (overfit risk). Breadth first.
- Keep everything isolated under `trader/fvm/`; never touch the LRExtrema live path.
