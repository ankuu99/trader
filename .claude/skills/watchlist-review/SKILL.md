---
description: Monthly/quarterly watchlist review — runs a fresh backtest, a deterministic falling-knife trend guard, and (where warranted) the qualitative `qualify` gate for each stock, then produces a Keep/Watch/Calibrate/Remove recommendation report saved to reviews/. Pass a single NSE:SYMBOL to instead run a deep-dive review of just that one stock.
argument-hint: [NSE:SYMBOL] [--skip-refresh]
---

Perform a full quantitative + qualitative review of the trading watchlist — or, if
the user passed a single `NSE:SYMBOL`, a deep-dive review of just that one stock.

## Mode selection (do this first)

Inspect `$ARGUMENTS`:
- **If it contains a stock symbol** (anything matching `NSE:XXX`, or a bare ticker
  like `MARICO` / `TATAMOTORS` that is clearly one stock) → follow
  **§ Single-stock deep dive** below and stop. Do not run the watchlist-wide flow.
- **Otherwise** (no symbol, possibly just `--skip-refresh`) → follow the
  **§ Watchlist review** flow (Steps 1–6).

---

# § Single-stock deep dive

Use this when the user names one stock (e.g. `/watchlist-review NSE:MARICO`). The
stock need not be in the watchlist — this works for evaluating candidates too.

## SD-1 — Run the detailed quant

```bash
python scripts/watchlist_review.py --symbol <NSE:SYMBOL> 2>/dev/null
```

(Append `--skip-refresh` if the user passed it; otherwise the token auto-refreshes.)

This emits JSON for the one stock with richer breakdowns than a watchlist row:
- `full` / `recent` — metrics for the full period and last 6 months
- `yearly` — per-calendar-year metrics (pnl, trades, win_rate, avg_win, avg_loss)
- `monthly_recent` — per-month metrics over the last 6 months
- `reasons` — exit-reason breakdown (count + total + avg P&L per `SL`/`TARGET`/`TRAILING`/`STRATEGY`/`PATTERN_TOP`/`OPEN@END`)
- `trades` — the full chronological trade list
- `override` / `params_used` — the active per-stock override (if any) and the effective params
- `in_watchlist` — whether the stock is currently traded

If the JSON has an `error` key, report it (bad symbol / no candles) and stop.

## SD-2 — Qualification gate (structural + qualitative)

Run the `qualify` skill on this stock instead of a bare news search. It pairs the
deterministic falling-knife trend guard (`scripts/trend_guard.py`) with diverse qualitative
sources (exchange filings, credit-rating actions, promoter pledge, event window,
governance/sector) and returns a **FIT / WATCH / AVOID** verdict:

```
Skill("qualify", "<NSE:SYMBOL>")
```

Fold its verdict into the deep-dive: an **AVOID** here overrides a healthy-looking backtest —
backtests are regime-blind, so a stock that traded well can be in a secular decline now (the
RMDRIP lesson: every dip in a one-way drop looks like a local minimum). Cite the decisive
reason in the report's "News & context" section.

## SD-3 — Replay diagnostics (optional but recommended)

If the quant shows a problem worth diagnosing — e.g. exits dominated by `SL` or
`OPEN@END`, weak win rate, or a declining recent trend — run the `replay` skill on
the same symbol to inspect the model's per-candle P(min)/P(max) behaviour and
identify missed exits or false entries:

```
Skill("replay", "<NSE:SYMBOL>")
```

## SD-4 — Write the deep-dive report

Save to `reviews/stock_<SYMBOL>_YYYYMMDD.md` with this structure:

```markdown
# Stock Deep Dive — <SYMBOL> — DATE

## Verdict
**<KEEP / WATCH / CALIBRATE / REMOVE / SKIP (candidate)>** — one-line rationale.

## Performance
| Period | P&L | Trades | Win rate | Avg win | Avg loss |
|--------|-----|--------|----------|---------|----------|
| Full   | ₹X  | N      | X%       | ₹X      | ₹X       |
| Recent 6m | ₹X | N    | X%       | ₹X      | ₹X       |

## Year-by-year
| Year | P&L | Trades | Win rate |
|------|-----|--------|----------|

## Exit breakdown
| Reason | Trades | Total P&L | Avg P&L |
|--------|--------|-----------|---------|
(Comment on whether exits are healthy — trailing/pattern-top dominating is good;
SL or OPEN@END dominating is a red flag.)

## Config
- In watchlist: yes/no
- Active override: <yaml snippet or "none (global params)">

## News & context
- Bullet the material findings from SD-2.

## Replay findings (if run)
- Key observations from SD-3.

## Recommendation
- Concrete next action: keep as-is / calibrate (which params) / remove / add to watchlist / skip.
```

## SD-5 — Offer follow-up actions

Print the verdict + key numbers to the terminal, then offer (do NOT act without confirmation):
1. If the stock looks miscalibrated → "Run /calibrate on <SYMBOL>?" — if yes, `Skill("calibrate", "<NSE:SYMBOL>")`.
2. If it's a strong candidate not yet traded → "Add <SYMBOL> to the watchlist in config.yaml?" — if yes, edit `config/config.yaml`.
3. If it's a current watchlist stock that should go → "Remove <SYMBOL> from the watchlist?" — if yes, edit `config/config.yaml`.

Do NOT modify `config/config.yaml` without explicit confirmation.

---

# § Watchlist review

Perform a full quantitative + qualitative review of the current trading watchlist.

## Step 1 — Run quant analysis

Run the following command. If the user passed `--skip-refresh` as an argument use `--skip-refresh`, otherwise run without it (which auto-refreshes the Kite token via TOTP):

```bash
python scripts/watchlist_review.py $ARGUMENTS 2>/dev/null
```

This fetches fresh candles, runs a full-period backtest (2023-01-01 → today) and a recent 6-month backtest, and prints JSON with per-stock metrics. Parse the JSON output.

## Step 2 — Classify each stock

Using the JSON data, classify each stock:

| Label | Criteria |
|-------|----------|
| **REMOVE** | full.pnl < 0 with no viable calibration path, OR trend=declining AND recent.pnl < -₹3,000 |
| **CALIBRATE** | full.pnl > 0 but trend=declining AND recent.pnl negative, OR recent.trades = 0 (no signals in 6m) |
| **WATCH** | trend=declining but recent.pnl still positive, OR sparse full.trades (< 10) |
| **KEEP** | full.pnl > 0, trend=stable or improving, adequate trade count |

## Step 3 — Structural + qualitative gate

Don't blindly run a full multi-source qualitative search for every name — that's wasteful.
Gate it: a cheap deterministic check for all, the deep `qualify` gate only where warranted.

### 3a — Trend guard + fundamental panel for every stock (cheap, deterministic)

Run **both** deterministic checks on each watchlist symbol — neither costs a web search and
both are reproducible:

```bash
python scripts/trend_guard.py --symbol <NSE:SYMBOL> --fetch --json 2>/dev/null
python scripts/fund_panel.py  --symbol <NSE:SYMBOL> --json 2>/dev/null
```

- **Trend guard** — a `FALLING_KNIFE` or `DOWNTREND` `structural_verdict` is an immediate
  escalation toward **REMOVE**, regardless of backtest P&L — the regime mismatch the backtest
  can't see.
- **Fund panel** — record `fund_verdict` + `quality_score`. Use it **two-sidedly**:
  a `DISTRESS` verdict or `high`-severity red flag escalates toward **REMOVE** (the dip may not
  recover); a `STRONG` panel is positive evidence to **KEEP** even on an `UPTREND`/declining-trend
  guard (a quality compounder's pullbacks mean-revert — the CUPID case). It auto-fetches names
  not yet ingested and suppresses leverage/cash flags for financials (M&MFIN, LTF).

### 3b — Full qualitative gate only for stocks that need it

Invoke the `qualify` skill (filings, rating actions, pledge, events, governance) **only** for
stocks that are not already clean — i.e. any of:
- trend guard = `FALLING_KNIFE` / `DOWNTREND` / `WATCH_RECOVERING`, OR
- fund panel = `DISTRESS` / `WEAK` (or any high-severity red flag), OR
- Step-2 class = `REMOVE` / `CALIBRATE` / `WATCH`, OR
- trend guard `confidence` = `low`.

```
Skill("qualify", "<NSE:SYMBOL>")
```

For stocks clean on both (Step-2 `KEEP` **and** trend guard `RANGE_BOUND` with adequate
confidence), a single light news scan (`NSE <SYMBOL> stock news <CURRENT_YEAR>`) is enough —
reserve the deep-gate budget for the names actually at risk.

### 3c — Fold the verdicts into the classification

Upgrade/downgrade each stock's Step-2 label using the gate: a `qualify` **AVOID** → `REMOVE`;
a **WATCH** → at least `WATCH`. Disagreements between quant P&L and the gate are the most
informative cases (e.g. good backtest but a fresh rating downgrade) — call them out explicitly
in the report.

## Step 4 — Write the report

Save a markdown report to `reviews/watchlist_review_YYYYMMDD.md` with this structure:

```markdown
# Watchlist Review — DATE

## Portfolio Summary
| Metric | Value |
|--------|-------|
| Full period P&L | ₹X |
| Return | X% |
| Trades | X |
| Recent 6m P&L | ₹X |
| Stocks profitable (recent) | X/Y |

## Recommendations

### ✅ KEEP
| Stock | Full P&L | Recent P&L | Trend | WR | Guard | Fund | Gate | News |
|-------|----------|------------|-------|----|-------|------|------|------|

### 👀 WATCH
| Stock | Full P&L | Recent P&L | Trend | WR | Guard | Fund | Gate | Concern |
|-------|----------|------------|-------|----|-------|------|------|---------|

### 🔧 CALIBRATE
| Stock | Full P&L | Recent P&L | Trend | WR | Guard | Fund | Gate | Action |
|-------|----------|------------|-------|----|-------|------|------|--------|

### ❌ REMOVE
| Stock | Full P&L | Recent P&L | Trend | Guard | Fund | Gate | Reason |
|-------|----------|------------|-------|-------|------|------|--------|

(`Guard` = trend_guard structural verdict; `Fund` = fund_panel verdict + quality_score;
`Gate` = `qualify` FIT/WATCH/AVOID where run.)

## New Candidates
(Stocks worth screening based on sector research or news)

## Suggested Actions
- [ ] Remove: ...
- [ ] Calibrate: ...
- [ ] Screen new candidates: ...
```

## Step 5 — Print summary and ask before acting

Print a condensed summary table to the terminal showing all four buckets.

Then ask the user:
1. "Remove these stocks from the watchlist? [list REMOVE stocks]" — if confirmed, edit config.yaml
2. "Run calibration for CALIBRATE stocks? [list them]" — if confirmed, proceed to Step 6

Do NOT modify `config/config.yaml` without explicit confirmation.

## Step 6 — Auto-calibrate flagged stocks (if user confirmed)

For each stock in the CALIBRATE bucket, invoke the calibrate skill in sequence:

```
Use the Skill tool to invoke "calibrate" with the symbol as argument.
Example: Skill("calibrate", "NSE:MARICO")
```

After each calibration completes, show the result and ask whether to apply the override before moving to the next stock. This keeps the user in control stock-by-stock rather than applying everything blindly.

Once all calibrations are done, summarise all applied overrides and suggest running a full backtest to confirm the portfolio-level impact.
