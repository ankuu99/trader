---
description: Monthly/quarterly watchlist review — runs fresh backtest, searches recent news for each stock, and produces a Keep/Watch/Calibrate/Remove recommendation report saved to reviews/. Pass a single NSE:SYMBOL to instead run a deep-dive review of just that one stock.
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

## SD-2 — News search

Search recent news for this one stock: `NSE [SYMBOL] stock news outlook 2025 2026`.
Look for earnings surprises, guidance cuts, SEBI/regulatory actions, promoter
pledging, sector tail/headwinds, and management/governance changes.

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

## Step 3 — News search for each stock

For every stock in the watchlist, search for recent news:

Query format: `NSE [SYMBOL] stock news outlook 2025 2026`

Look for:
- Earnings surprises, profit warnings, or guidance cuts
- Regulatory issues, SEBI actions, promoter pledging
- Sector tailwinds/headwinds (policy changes, commodity moves, competition)
- Management changes or corporate governance concerns

Upgrade or downgrade the classification if news materially changes the picture (e.g. good quant but active SEBI investigation → WATCH).

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
| Stock | Full P&L | Recent P&L | Trend | WR | News |
|-------|----------|------------|-------|----|------|

### 👀 WATCH
| Stock | Full P&L | Recent P&L | Trend | WR | Concern |
|-------|----------|------------|-------|----|---------|

### 🔧 CALIBRATE
| Stock | Full P&L | Recent P&L | Trend | WR | Action |
|-------|----------|------------|-------|----|--------|

### ❌ REMOVE
| Stock | Full P&L | Recent P&L | Trend | Reason |
|-------|----------|------------|-------|--------|

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
