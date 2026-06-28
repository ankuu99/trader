---
description: Qualify a stock for the LRExtrema strategy — a forward-looking, disqualifier-oriented gate that pairs a deterministic falling-knife trend guard with diverse qualitative sources (corporate filings, rating actions, promoter pledge, event calendar, governance/sector news) to produce a FIT / WATCH / AVOID verdict. Advisory only — never changes trading. Pass one NSE:SYMBOL.
argument-hint: NSE:SYMBOL [--cache-only]
---

Decide whether the LRExtrema strategy should be allowed to trade a stock **going forward** —
a different question from "did it backtest well" (backtests are regime-blind; a stock that
oscillated profitably can be in a secular decline now — the RMDRIP failure: every dip in a
one-way drop looks like a local minimum).

## Core principle — this is a DISQUALIFIER, not a picker

LRExtrema is **mean-reversion on range-bound / oscillating stocks**. It FAILS on sustained
one-way trends. So:
- Do **not** rank stocks by forward *growth* — high-growth momentum names trend and have few
  local minima (weak fit). The goal is *structural soundness*, not upside.
- Use qualitative signals **asymmetrically**: news rarely proves a stock is great to trade, but
  it reliably tells you when to **avoid** one. Weight red flags heavily; treat positive
  narrative as weak evidence.
- Prefer **primary filings over secondary commentary**, and **timestamp every source** — LLM
  news synthesis is prone to staleness and narrative over-weighting, which is dangerous near money.

Require a stock symbol in `$ARGUMENTS` (e.g. `NSE:MARICO`). If none given, ask for one and stop.

---

## Step 1 — Deterministic structural guard (quant, free, reproducible)

```bash
python scripts/trend_guard.py --symbol <NSE:SYMBOL> --fetch --json 2>/dev/null
```

(Use `--cache-only`'s equivalent — drop `--fetch` — only if the user passed `--cache-only` or the
token can't refresh. With `--fetch` it pulls ~18 months and auto-refreshes the Kite token.)

Parse the JSON. Key fields: `structural_verdict` (`FALLING_KNIFE` / `DOWNTREND` /
`WATCH_RECOVERING` / `UPTREND` / `RANGE_BOUND`), `drawdown_from_peak_pct`,
`trailing_returns_pct`, `confidence`.

- `FALLING_KNIFE` or `DOWNTREND` → strong lean toward **AVOID**; the qualitative step should
  explain the *cause* (and only an exceptional, well-evidenced turnaround overrides it).
- `confidence: low` → note it; lean harder on the qualitative read.

## Step 2 — Corporate announcements & filings (highest signal)

Search for recent exchange filings / announcements:
- `NSE BSE <COMPANY> corporate announcements <CURRENT_YEAR>`
- `<COMPANY> auditor resignation OR CFO resignation OR board change <CURRENT_YEAR>`

Red flags (any one is serious): auditor/CFO/independent-director resignations, qualified audit
opinion, delayed results, related-party-transaction concerns, debt restructuring, loan defaults.

## Step 3 — Credit rating actions (best falling-knife predictor)

Search: `<COMPANY> CRISIL OR ICRA OR CARE rating <CURRENT_YEAR>`

A **downgrade**, "rating watch negative", or "default (D)" is a high-confidence AVOID signal —
especially if it corroborates a `FALLING_KNIFE`/`DOWNTREND` guard.

## Step 4 — Fundamental panel (structured, PIT — prefer over web search)

Run the deterministic two-sided fundamental panel. It pulls Trendlyne financials +
shareholding from `fvm.db` (auto-fetching the stock on demand if absent, including small-caps
outside the Nifty500 universe like CUPID), and returns BOTH distress red-flags AND a quality
score — point-in-time, reproducible, and far more reliable than LLM news synthesis for numbers:

```bash
python scripts/fund_panel.py --symbol <NSE:SYMBOL> --json 2>/dev/null
```

Parse the JSON. Key fields: `fund_verdict` (`STRONG`/`OK`/`WEAK`/`DISTRESS`/`INSUFFICIENT`),
`quality_score` (0–1, absolute thresholds — NOT the FVM cross-sectional composite), `red_flags`
(pledge spike, promoter selling, profit collapse, leverage/coverage/cash distress), `positives`
(growth, margin expansion, ROCE, low leverage, no pledge), `financial` (if true, lender flags
are suppressed as structural), `notes`.

Use it **two-sidedly** (this is the key reframe):
- A **`DISTRESS`** verdict or any `high`-severity red flag → strong lean toward **AVOID** — the
  business may not support a dip recovery (falling-knife risk the backtest can't see).
- A **`STRONG`** verdict (durable growth, low leverage, clean ownership) → *positive* evidence
  the stock is a good LRExtrema fit **even in an uptrend** — quality is exactly what makes a
  pullback mean-revert rather than continue (the CUPID case). Do NOT treat quality as irrelevant
  to a mean-reversion strategy.

If `fund_verdict` is `INSUFFICIENT` (not in Trendlyne master / stale cookie), fall back to a web
search (`<COMPANY> promoter pledge shareholding pattern latest quarter`) and the logged-in
Trendlyne browser session for pledge/holding trend. Red flags: rising pledged %, falling
promoter holding, large insider selling (CLAUDE.md notes low/pledged promoter holding as
pump-and-dump risk).

## Step 5 — Event-window check

Search: `<COMPANY> results date OR AGM OR record date OR bonus OR split <CURRENT_MONTH> <CURRENT_YEAR>`

Flag any earnings / AGM / record-date window in the next ~2 weeks — these distort candle
patterns and the strategy should avoid fresh entries around them (documented in CLAUDE.md).

## Step 6 — Governance & sector context

Search: `<COMPANY> SEBI OR fraud OR investigation news` and `<SECTOR> sector outlook <CURRENT_YEAR>`

Capture SEBI actions, litigation, accounting allegations, and whether the sector has a structural
headwind (the macro reason a stock may keep declining).

---

## Step 7 — Synthesize the verdict

Combine the quant guard (Step 1), the fundamental panel (Step 4), and qualitative findings
(Steps 2,3,5,6). Distress/red-flag evidence takes the **worse** of the views — a clean chart
with an auditor resignation or a `DISTRESS` panel is still AVOID. But a `STRONG` fundamental
panel can *upgrade* a stock the trend guard alone would treat as a weak fit (a quality uptrend).

| Verdict | When |
|---------|------|
| **AVOID** | `FALLING_KNIFE`/`DOWNTREND`, panel `DISTRESS`/high-severity red flag, OR any serious qualitative red flag (rating downgrade, auditor/CFO exit, SEBI action, pledge spike, structural sector decline) |
| **WATCH** | `WATCH_RECOVERING`/`low confidence`, panel `WEAK`/`INSUFFICIENT`, OR soft concerns (mild deterioration, mixed news, imminent event window) — re-check before adding/keeping |
| **FIT** | (`RANGE_BOUND` with adequate confidence **OR** `UPTREND` backed by a `STRONG` panel) AND no material red flags. A quality compounder whose dips reliably recover is a *good* fit even trending up (CUPID) — do not auto-downgrade an uptrend. |

Disagreements between quant and qualitative are the most informative cases — call them out
explicitly (e.g. "chart is range-bound but a rating downgrade landed last week → AVOID").

## Step 8 — Write the report

Save to `reviews/qualify_<SYMBOL>_YYYYMMDD.md`:

```markdown
# Stock Qualification — <SYMBOL> — DATE

## Verdict: **FIT / WATCH / AVOID**
One-line rationale. Note if quant and qualitative disagreed.

## Structural guard (quant)
- Verdict: <structural_verdict> (confidence <…>)
- Drawdown from peak: X% | trailing returns: 1m/3m/6m/12m
- Reading: <range-bound / falling knife / …>

## Fundamental panel (Step 4)
- Verdict: <fund_verdict> | quality_score: <0–1> | source: <fvm.db/fetched/none>
- Red flags: <list or none> | Positives: <list>
- Reading: <distress → dip won't recover / quality → dip is buyable / financial-sector note>

## Qualitative findings
| Source | Finding | Date | Signal |
|--------|---------|------|--------|
| Filings/announcements | … | YYYY-MM-DD | 🔴/🟡/🟢 |
| Credit rating | … | | |
| Promoter pledge / holding | … | | |
| Event window | … | | |
| Governance / sector | … | | |

## Recommendation
Concrete next action + the single most important reason.
```

## Step 9 — Advisory follow-up (do NOT act without confirmation)

This skill is advisory only. After printing the verdict + the decisive reason to the terminal:
- If **AVOID** and the stock is in the watchlist → ask "Remove <SYMBOL> from the watchlist?"
  and only edit `config/config.yaml` if confirmed.
- If **FIT** and it's a candidate → suggest `/calibrate <SYMBOL>` then paper-trading before adding.
- If **WATCH** → state exactly what to re-check and when.

Never modify `config/config.yaml` or trading behavior automatically.
