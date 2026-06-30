# FVM — Forward Plan (next steps, persists across sessions)

**Read this first on resume.** Companion to `FVM_Progress.md` (status log). This file is the
ordered to-do; `FVM_Progress.md` is what's already done. Last updated 2026-07-01.

## Where we are — MILESTONE A IS A CONCLUSIVE FAIL (2026-07-01). Decision needed: repurpose-or-shelve.
- Strategy + harness fully BUILT & tested (78 pytests). Phases 0–4 + Milestone-A walk-forward.
- **The decisive run:** with the annual-fallback (§ below) the walk-forward now spans **2019→2026,
  28 folds, ALL regimes incl. the Mar-2020 COVID crash.** Result: beats benchmark **3/28 (11%)**,
  profitable 20/28 (71% — ~tautological for long-only equity in a mostly-up decade), **mean edge
  −29.0pp (FVM +17.6% vs bench +46.6%).** GATE = **FAIL**, now conclusively.
- **The defensive-overlay thesis is BURIED, not confirmed.** In the one real crash fold
  (2019-07→2020-03) FVM LOST MORE than momentum (−14.8% vs −12.8%), and it beat momentum in only 2
  of 4 negative-benchmark folds. So FVM is *reliably profitable but not reliably defensive*, and
  *never reliably beats momentum*. The earlier "inconclusive because bull-only" caveat is RESOLVED:
  we got the bear/crash regimes, FVM still fails.
- **DO NOT** chase more breadth, **DO NOT** tune to flip (standing rule), **DO NOT** do the BSE deep-
  quarterly scrape — the annual-fallback already answered the regime question; BSE would only sharpen
  an already-clear FAIL. The data is no longer the bottleneck; the *strategy spec* is.

### THE DECISION (this is the actual next step — needs the user)
Rules-only FVM does not clear the gate. Three honest options, in recommended order:
- **(A) Shelve FVM-as-standalone.** It is not an edge over momentum. Stop here; the harness/UI/data
  pipeline remain valuable as a fundamentals research cockpit (`fvm_shortlist.py`, the Streamlit app).
- **(B) Repurpose as a quality/risk FILTER on the LRExtrema sleeve** — but treat skeptically and
  validate independently: the crash underperformance undercuts the "drawdown protection" rationale,
  so do NOT assume it helps; A/B it on LRExtrema entries before trusting it.
- **(C) Phase 6 ML challenger** — only if (A)/(B) are unsatisfying; deferred + treat skeptically
  (meta-labeling worsened LRExtrema before).
- Phase 5 (live FVM sleeve) stays **gated and now effectively shelved** unless (B) is validated.

## The plan (ordered — top of the list is the critical path)

### 1. Re-order the ingest to prioritise MID-CAPS  ✅ DONE (2026-06-28)
Implemented via size-band index membership (the deliberate route, not a price proxy). Ingested
**NIFTY Midcap 150 + Smallcap 250** constituents one-shot (`universe.ingest_size_memberships`);
`universe.prioritized_universe` re-orders the eligible NIFTY500 set **mid → small →
large-remainder** (NIFTY500 = NIFTY100 ∪ Midcap150 ∪ Smallcap250, a disjoint partition).
`scripts/fvm_ingest.py` now ingests from that order, so the daily quota fills mid-caps first.
Verified: eligible 399 = 114 mid + 208 small + 77 large; the next ~75 names to ingest are all
mid-caps. 2 new unit tests (`test_prioritized_universe_*`). Membership already written to fvm.db.

### 2. Run the daily fundamentals ingest until the universe fills  ✅ effectively DONE for the gate
- `python scripts/fvm_ingest.py` after each Trendlyne quota reset (~40 stocks/day, resumable,
  mid-caps first). **138/399 scored as of 2026-06-30** — enough breadth that the gate is now
  power-limited by REGIME, not name count. Keep topping up opportunistically, but it's no longer
  the blocker. Needs a fresh `TRENDLYNE_COOKIE` in `config/.env` if financials 403.

### 3. Re-run the price cache after each batch  ✅ DONE (138/139 cached, 2026-06-30)
- `python scripts/fvm_prices.py` (cache-only is cheap; only fetches newly-scoreable names). Only
  GAYAPROJ short (the -BE name). Re-run after any future ingest batch.

### 4. Re-run the Milestone-A gate as coverage grows  ✅ DONE at 138 names (2026-06-30) — FAIL
- Result above: 1/6 beats bench, mean edge −15.1pp, confirmed defensive overlay. Breadth did not
  help. **NO parameter tuning** — standing rule; flipping a 6-fold bull-only window is overfit.
- Don't re-run the gate again on more breadth alone — it won't change the regime problem. Re-run
  ONLY after step 5 extends the window into a real drawdown.

### 5. Get a multi-regime backtest window  ← NOW THE CRITICAL PATH
The 2023-03 quarterly wall is the binding constraint: it makes the only testable window a single
bull regime where a defensive overlay structurally cannot beat momentum, so the current FAIL is
**inconclusive**. Status:

- ~~Probe Trendlyne for deeper quarterly~~ ❌ DEAD END (2026-07-01). Reverse-engineered the website
  endpoint `get-fundamental_results-v2/<id>/<hash>/`; it returns **the same 13 quarters / 2023-03**
  as Excel-Connect (RADICO test: 13q Mar23→Mar26). 13q is Trendlyne's hard cap everywhere. Don't
  re-investigate. (See [[project_fvm_trendlyne_depth_and_annual_fallback]].)
- **(fast read) Annual-fallback for the crown-jewel yoy** ✅ IMPLEMENTED + RUN (2026-07-01), zero new
  data. `factors.floored_yoy_series` falls back to annual NP/revenue (reach 2013) when quarterly is
  absent (pre-2023). Live unchanged (always quarterly); only the historical window uses it. Window
  now spans **2019→2026, 28 folds incl. Mar-2020 crash → CONCLUSIVE FAIL** (3/28 beat, edge −29pp;
  see "Where we are" above). This was the decisive test and it answered the question.
- **(rigorous) BSE XBRL deep quarterly** — ❌ NOT WORTH DOING. The annual-fallback already gave the
  multi-regime answer (FAIL); true-PIT quarterly would only sharpen an already-clear negative.
- **(escape hatch → now the live decision)** Repurpose FVM as a risk/quality filter on LRExtrema, or
  shelve. See "THE DECISION" above.

### 6. Manual-investing shortlist CLI  ✅ DONE (2026-06-28)
`scripts/fvm_shortlist.py` — runs scoring + vetoes + technical as-of a date over the ingested
universe and prints (1) FVM CANDIDATES (names clearing fundamentals+trend+timing, ranked as the
strategy ranks) and (2) FULL BOARD by composite with a per-name decision tag
(CANDIDATE / NO_TIMING / NO_TREND / WEAK_FUND / VETOED). `--asof`, `--top`, `--verbose`.
Usable now on the 39 names; gets meaningful as the universe fills (steps 1–3).

### 6b. FVM Cockpit UI  (U0–U4 DONE 2026-06-28 — U5 pending, post-Phase-5)
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
4. **Milestone-A / Validation** ✅ — button-gated walk-forward run (cached); gate verdict banner,
   summary metrics, FVM-vs-benchmark continuous equity curve, per-fold table (coloured edge),
   down-vs-up regime split (exposes the defensive-overlay character). Fold length/stride/capital
   sliders.
5. **Scoring Lab** ✅ — composite distribution (with Gate-A cut + floor lines), pillar
   contributions, per-factor coverage/NaN + mean-normalized heatmap (flags thin factors),
   gate-sensitivity sliders (pctile_cut / floor / trend_floor) → live funnel
   (universe→veto→Gate-A→Gate-B→trigger→candidates).
6. **Portfolio / Live** — open positions, sleeve capital, exit-stack state (placeholder until Phase 5).

Build phasing: ~~**U0** scaffold + cached scoring-sweep helper~~ ✅ → ~~**U1** Shortlist + Stock
Detail~~ ✅ (`scripts/fvm_ui.py` + `trader/fvm/ui/data.py`, `streamlit run scripts/fvm_ui.py`) →
~~**U2** Coverage~~ ✅ → ~~**U3** Milestone-A viewer~~ ✅ → ~~**U4** Scoring Lab~~ ✅ → **U5**
Portfolio/Live (deferred until Phase 5 lands; + Flask live monitor)
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
