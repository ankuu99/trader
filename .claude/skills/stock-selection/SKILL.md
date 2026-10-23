---
name: stock-selection
description: "How to find, screen and shortlist NSE stocks for LRExtremaStrategy — screen.py → calibrate.py → paper workflow, how to read the screening CSV (good-candidate thresholds and red flags), fundamental/market context to layer on top, and watchlist rules. Use when interpreting screen results or judging whether a stock belongs on the watchlist."
---

# Stock selection guidance

## Goal
Find NSE-listed equity stocks where the LRExtremaStrategy has historically generated profitable trades with the current (or calibrated) parameters.

## Primary workflow
1. Run `screen.py` over a representative backtest period (minimum 6 months, ideally 1–2 years)
2. Filter the results CSV for candidates worth investigating further
3. Run `calibrate.py` on promising candidates to find their optimal parameters
4. Paper trade candidates for 2–4 weeks before adding to live watchlist

## Screening result interpretation

The output CSV has columns: `symbol, total_trades, wins, losses, win_rate, total_pnl, return_pct, avg_win, avg_loss, sharpe_proxy`

**Good candidate signals:**
- `return_pct > 5%` over the backtest period (net of all costs)
- `win_rate >= 50%` — the strategy should be right more often than wrong
- `total_trades >= 3` — enough trades to have statistical signal (not just one lucky trade)
- `avg_win / abs(avg_loss) > 1.5` — wins should be meaningfully larger than losses (R:R)
- `sharpe_proxy > 0.3` — consistent, not just a few big wins masking many losses

**Red flags to exclude:**
- `total_trades == 1` — a single trade result is noise
- `total_pnl > 0` but `win_rate < 30%` — one outlier win masking systematic losses
- Very high `total_trades` with low `return_pct` — churning; transaction costs eating gains
- Stocks with erratic volume (check manually — `screen.py` doesn't filter for this)

## Fundamental / market context to layer on top
The screener is purely quantitative. When shortlisting, also consider:
- **Sector momentum**: prefer stocks in sectors with broad market tailwind
- **Liquidity**: daily average volume should be at least ₹50L turnover to ensure LIMIT orders fill without slippage
- **Corporate events**: avoid stocks near earnings, AGM, bonus/split record dates — these create abnormal candle patterns that confuse the model
- **Promoter holding**: very low promoter holding stocks can be targets for pump-and-dump, generating false extrema signals

## Watchlist management
- `watchlist` in config.yaml — stocks actively traded by the system
- Add a stock to `watchlist` only after calibration + paper trading validation

---
