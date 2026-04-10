# Trader Codebase Review

## Overview
This review summarizes the key issues identified across the trader codebase. The codebase is generally well-structured, but there are several correctness, reliability, and risk issues that should be addressed.

## Critical Issues

1. **Division by zero in RSI calculation**
   - File: `trader/strategies/rsi.py`
   - Problem: `avg_loss == 0` is guarded, but `avg_gain / avg_loss` can still happen when the slice is empty or values are not handled properly.
   - Impact: Strategy crash on the first candle or when no losses exist.

2. **Division by zero in paper fill slippage warning**
   - File: `trader/orders/manager.py`
   - Problem: Logging computes `slippage / order.price_hint * 100` even when `order.price_hint == 0`.
   - Impact: Order fill callback can crash, blocking risk/portfolio updates.

3. **Race condition in live candle assembly**
   - File: `trader/data/live.py`
   - Problem: `self._emit_candle()` calls external handlers while holding a lock.
   - Impact: Blocks tick processing, may drop ticks and corrupt candle assembly.

4. **Backtest stop-loss fill optimism**
   - File: `trader/backtest/engine.py`
   - Problem: SL fills always use the exact SL price instead of a more realistic fill if the candle range exceeded the stop.
   - Impact: Backtest P&L is optimistic and not representative of live execution.

## High Priority Issues

5. **EMA Pullback strategy can compute EMA without enough data**
   - File: `trader/strategies/ema_pullback.py`
   - Problem: No guard for empty or insufficient `closes` list.
   - Impact: Incorrect EMA and invalid signals.

6. **Breakout strategy can crash on startup**
   - File: `trader/strategies/breakout.py`
   - Problem: Calls `max(prev_closes)` when `prev_closes` may be empty.
   - Impact: Strategy fails during early warm-up.

7. **Quantity calculation may return zero silently**
   - File: `trader/risk/manager.py`
   - Problem: `int(config.max_risk_per_trade // sl_distance)` can produce 0 with a very wide stop-loss.
   - Impact: Valid signals get silently rejected without a warning.

## Moderate Issues

8. **Inconsistent stop-loss fallback when ATR is unavailable**
   - File: `trader/risk/manager.py`
   - Problem: Uses a fixed 1% price fallback for all strategies when ATR is missing.
   - Impact: Uneven risk sizing across strategies and instruments.

9. **Portfolio and risk manager P&L may diverge**
   - File: `trader/portfolio/tracker.py`
   - Problem: Paper-mode P&L is computed separately in `PortfolioTracker` and `RiskManager`.
   - Impact: Different P&L values may appear in logs and reports.

10. **Config singleton lacks required-key validation**
    - File: `trader/core/config.py`
    - Problem: `strategy_config()` returns `{}` for missing sections instead of raising.
    - Impact: Missing config keys cause cryptic failures in strategy initialization.

11. **SQLite transaction/journal growth risk**
    - File: `trader/data/store.py`
    - Problem: `conn.commit()` on every context exit may create large journal files during busy writes.
    - Impact: Disk usage may grow unexpectedly on heavily used systems.

12. **Timezone issues in historical warm-up**
    - File: `trader/data/historical.py`
    - Problem: Uses `datetime.now()` local system time instead of IST.
    - Impact: Wrong candle ranges on non-IST machines.

13. **No automatic access token refresh**
    - File: `trader/auth/session.py`
    - Problem: Token expiry at midnight IST is not handled automatically.
    - Impact: Trader may fail after 24 hours without manual login refresh.

## Minor Issues and Improvements

14. **Hardcoded IST in scheduler**
    - File: `trader/scheduler/jobs.py`
    - Problem: Timezone is fixed, with no override for other markets.
    - Impact: Limits portability to other regions.

15. **Supertrend ATR calculation may be wrong**
    - File: `trader/strategies/supertrend.py`
    - Problem: ATR calculation uses simple average and may index `closes` incorrectly.
    - Impact: Incorrect trend filter and stop levels.

16. **Backtest ignores gap risk**
    - File: `trader/backtest/engine.py`
    - Problem: Fills are assumed at exact next candle open.
    - Impact: Backtest results are too optimistic.

17. **Paper mode execution is too idealized**
    - File: `trader/orders/manager.py`
    - Problem: Paper orders fill at the next candle open with zero slippage.
    - Impact: Paper mode may overstate performance.

18. **Limited calibration validation**
    - File: `trader/calibration/runner.py`
    - Problem: Only EMA pullback constraints are checked.
    - Impact: Invalid parameter sets can still run.

19. **Order callback exceptions are swallowed**
    - File: `trader/orders/manager.py`
    - Problem: Exceptions in order update callbacks are logged but otherwise ignored.
    - Impact: Risk and portfolio updates may be lost silently.

## Recommendations

- Fix the critical division-by-zero and candle feed lock issues first.
- Adjust backtesting execution to better model realistic fills and gaps.
- Add stronger config validation, logging for rejected zero-quantity signals, and consistent P&L accounting.
- Consider improving paper mode realism with slippage and partial fills.

## Overall Assessment
The codebase is organized and mostly consistent with the documented architecture. However, the issues above are significant enough that they should be addressed before relying on the system for live trading or calibration.
