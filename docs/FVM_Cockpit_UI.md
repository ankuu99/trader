# FVM Cockpit — UI Guide

A research / manual-investing dashboard over the FVM (Fundamental-Value-Momentum) pipeline.
Its centrepiece is the **🔬 Stock Study** page — study one company in depth as a long-term
buy-and-hold candidate. It also scores the ingested universe, shows what the (now-shelved) timing
strategy would have acted on, tracks ingest coverage, and reports the Milestone-A gate.

> **The reframe (important).** The FVM *trading strategy* — timing entries to beat momentum — is a
> conclusive Milestone-A FAIL (see FVM_Progress.md: it never reliably beats momentum, even across
> 2018-26 incl. the COVID crash). But the *fundamental engine* it's built on is exactly what
> discretionary **long-term investing** needs: a consistent, point-in-time-correct way to judge
> business quality and rank a stock against its peers. The cockpit — above all the Stock Study page
> — is that engine repurposed as a research tool. It's decision-support and ammunition, not a
> mechanical signal; the qualitative judgment (does the moat last? is management honest?) is yours.

---

## Running it

```bash
source .venv/bin/activate
streamlit run scripts/fvm_ui.py        # opens http://localhost:8501
```

Most pages **read cached data only**. Populate the caches first:
- `python scripts/fvm_ingest.py`  → fundamentals + shareholding into `data/fvm.db`
- `python scripts/fvm_prices.py`   → daily candles into `data/market.db`

**Exception — the Stock Study page can fetch LIVE.** Type any NSE symbol that isn't cached and hit
*"Fetch live from Trendlyne + Kite"* and it pulls financials (Trendlyne fincsv), shareholding
(Screener) and prices (Kite) on demand, then studies it. That path needs a fresh `TRENDLYNE_COOKIE`
in `config/.env` and a valid Kite token (`scripts/kite_totp_refresh.py`).

The sidebar has an **As-of date** picker (everything is computed point-in-time as of that date —
only data knowable on/before it is used), a **page selector**, and a **Clear cache / refresh**
button (use it after a fresh ingest, since results are cached).

---

## Pages

### 🔬 Stock Study  *(home — long-term conviction)*
Study one company in depth, in one place, as a multi-year buy-and-hold candidate. Type any NSE
symbol (cached names are instant; uncached ones can be fetched live).

- **Conviction scorecard** — the heart of the page. Maps what serious long-term investors actually
  use — Buffett/Munger's **four M's** (Meaning · Moat · Management · Margin of safety) plus the
  quant quality screen — onto our point-in-time data, as five sections, each criterion graded
  **PASS / WATCH / FAIL / NA** with the value and a plain-English "why it matters":
  - **Quality & Returns** *(Moat)* — ROCE, ROE, ROCE trend, net-margin trend.
  - **Growth** *(Meaning)* — revenue & profit 5yr/3yr CAGR, growth momentum (3yr vs 5yr).
  - **Balance sheet & Cash** *(Survival)* — D/E, interest coverage, earnings quality (CFO/PAT), FCF.
  - **Management & Ownership** — promoter holding + trend, pledge, FII+DII trend, dividend payout.
  - **Valuation & Margin of Safety** — P/E, EV/EBITDA, PEG, position in the 1-yr range.
- **Red flags (Munger inversion)** — "what would guarantee failure?": the FVM vetoes (aggressive
  accounting = profit not backed by cash, manufactured earnings), parabolic extension, promoter
  pledging/selling — each with an explanation.
- **Multi-year trajectory** — revenue & profit, returns & margins (vs the 15% quality bar), earnings
  quality (CFO vs net profit), leverage (D/E + interest coverage), and ownership over time.
- **Peer comparison** — the subject's sector peers ranked head-to-head (composite, ROCE, ROE,
  growth, D/E, EV/EBITDA, promoter %) so you can answer *"which of these is the better business?"*.
- **Price/technical context** and the **FVM pillar/factor detail** are tucked into expanders.

It's evidence to reason over, not a buy/sell call — the qualitative moat/management judgment is yours.

### 1. Today's Shortlist  *(strategy view)*
What the strategy would act on, as of the selected date.

- **FVM candidates** — names that clear the *entire* pipeline (fundamentals Gate A + weekly trend
  Gate B + a daily timing trigger), ranked exactly as the strategy ranks them
  (within-pool fundamental percentile × technical score). Often empty — that's normal; it only
  fills on days a qualifying name also has a fresh pullback/breakout.
- **Full board** — every scored name by composite, each tagged with a one-word **decision**:

  | Tag | Meaning |
  |---|---|
  | `CANDIDATE` | clears everything — would act today |
  | `NO_TIMING` | fundamentals + trend OK, just no entry trigger today (the watchlist) |
  | `NO_TREND`  | fundamentals OK, but not a weekly uptrend (Gate B fail) |
  | `WEAK_FUND` | below the fundamental cut (Gate A fail) |
  | `VETOED`    | a red-flag veto fired |

  Filter by decision and sector, search by symbol. Pick a name at the bottom to jump to its detail.

### 2. Stock Detail  *(drill-down / explainability)*
Everything behind one name's score and decision.

- **Header** — composite, trend, timing, technical score, veto PASS/FAIL, decision badge; a
  parabolic-extension warning if the entry veto is active.
- **Fundamental pillars** — the five pillar scores (earnings / valuation / forward / ownership /
  balance sheet) as horizontal bars.
- **Technical charts** — weekly candles with the 40w/10w moving averages (Stage-2 trend), and
  daily candles with the 50d MA, the wide catastrophe stop, and volume.
- **Tabs** — full factor table (normalized score + raw value, colour-graded); PIT fundamentals
  history (revenue / net profit / OPM / EPS / CFO / D-E / ROCE); shareholding trend
  (promoter / FII / DII / pledge).

### 3. Universe & Coverage  *(ops — steer the ingest)*
How far the ingested universe is from the full ~399-name target.

- **Progress** — ingested / target, priced, missing count, quarterly-depth range, last ingest.
- **Ingested tab** — per name: quarter/annual period depth, shareholding flag, price bars + last
  date; auto-flags names with gaps (no price / no shareholding / shallow quarters).
- **Missing tab** — targets not yet ingested, with a CSV download to feed the daily quota.
- **By sector** — coverage % per sector (spot lopsided ingest — the sector-relative valuation
  factors need breadth within each sector).

### 4. Milestone-A  *(validation gate)*
The honest test: does rules-only FVM beat a naive-momentum benchmark on the same universe + cost
model, profitably, across rolling walk-forward folds?

- **Button-gated** — the walk-forward is heavy (~minutes on first run), then cached. Fold length,
  stride, and sleeve capital are adjustable.
- **Gate verdict** — PASS/FAIL banner (beat benchmark *and* profitable in the majority of folds),
  plus a thin-universe caveat that shows under 30 names.
- **Equity curve** — FVM vs benchmark over the full data-valid window.
- **Per-fold table** — return, edge, trades, win rate, max drawdown per fold.
- **Regime split** — mean edge in down/choppy folds vs up folds. A large positive edge in down
  folds with a negative edge in up folds = **defensive quality overlay** (wins drawdowns, lags
  momentum rallies) — the current read on the thin 39-name universe.

### 5. Scoring Lab  *(score anatomy + gate sensitivity)*
Why the scores look the way they do.

- **Composite distribution** — histogram with the Gate-A percentile cut and the absolute floor
  marked.
- **Pillar contributions** — mean weighted contribution of each pillar to the composite. A pillar
  pinned at weight×0.5 means no cross-sectional signal (usually missing data).
- **Factor coverage** — per factor: coverage % (names with a real value vs falling back to neutral
  0.5), and mean normalized score; thin factors (<50% coverage) are flagged.
- **Gate sensitivity** — sliders for the Gate-A pctile cut / floor and the Gate-B trend floor drive
  a live funnel: universe → pass-veto → Gate A → Gate B → trigger → candidates. Use it to
  *understand* the gates, not to tune them to a desired count (overfit risk on a thin universe).

### 6. Portfolio / Live  *(deferred)*
Open positions, sleeve capital, exit-stack state. Ships with Phase 5 (live integration), alongside
a separate Flask read-only live monitor.

---

## How it's built

- **`scripts/fvm_ui.py`** — Streamlit + Plotly app (the view layer + caching).
- **`trader/fvm/ui/data.py`** — framework-agnostic data layer (no Streamlit import, so it stays
  testable). Functions: `build_board`, `load_stock`, `coverage`, `milestone_a`, `scoring_lab` /
  `gate_counts`. Each calls only the tested `scoring` / `vetoes` / `technical` / `handoff` /
  `walkforward` functions and reads `fvm.db` + `market.db` cache-only.
- **Hard rule:** the UI reimplements no engine logic, and never touches the LRExtrema UI or the
  live trading path.

See `docs/FVM_Forward_Plan.md §6b` for the build phasing and `docs/FVM_Progress.md` for the session
log.
