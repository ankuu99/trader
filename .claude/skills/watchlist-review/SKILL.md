---
description: Monthly/quarterly watchlist review — runs fresh backtest, searches recent news for each stock, and produces a Keep/Watch/Calibrate/Remove recommendation report saved to reviews/
argument-hint: [--skip-refresh]
---

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
