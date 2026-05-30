# Autonomous Maintenance Plan

## Goal

Keep the system robust across market regimes: bull runs, corrections, and sideways periods.  
Three levers: **parameter recalibration**, **stock rotation**, and **periodic walk-forward validation**.

---

## Baseline (as of 2026-05-27)

| Metric | Value |
|--------|-------|
| Period | 2020-01-01 → 2026-05-27 |
| Return | **150.47%** |
| 2025 return (correction year) | **40.38%** |
| Win rate | 65.7% |
| Profit factor | 1.65 |
| Max drawdown | 13.6% (₹40.8k) |
| Sortino | 0.342 |
| TRAILING exits | 299 / 623 (48%) |
| PATTERN_TOP exits | 35 / 623 (6%) |
| SL exits | 115 / 623 (18.5%) |
| STRATEGY (timeout) exits | 172 / 623 (27.6%) |

**Watchlist (14 stocks):**
- ATHERENERG, CUPID, GOKEX, POLYCAB, IRCTC, INDUSINDBK, ASTRAL, NTPC, IDFCFIRSTB, ANGELONE, CDSL, SBIN, BAJAJFINSV, CHOLAFIN

**Strategy params (key):**
- `threshold`: 0.90, `profit_pct`: 7, `trail_pct`: 1.5, `stop_pct`: 10, `hold_bars`: 400
- `sell_threshold`: 0.70, `sell_min_pct`: 12.0, `ema_gate_enabled`: true, `ema_gate_period`: 25

---

## Maintenance Schedule

### Monthly (5 min each month-end)

**1. Check live P&L vs baseline:**
```bash
# Inspect logs or DB for monthly P&L
```
- If monthly return < -5%: flag for immediate review
- If 3 consecutive months negative: run full parameter recalibration (see below)

**2. Check per-stock STRATEGY exit rate:**
```bash
python scripts/backtest.py --from <3-months-ago> --cache-only 2>/dev/null | tail -40
```
- If a stock shows >80% STRATEGY exits over 3 months → candidate for removal
- If a stock shows SL-only exits (all SL, zero TRAILING) → consider removing

---

### Quarterly (30 min each quarter-end)

**1. Run backtest over the past 6 months:**
```bash
python scripts/backtest.py --from <6-months-ago> --cache-only 2>/dev/null | tail -60
```

**Target thresholds for rolling 6-month performance:**
| Metric | Keep | Review | Remove Stock |
|--------|------|--------|--------------|
| Per-stock return | >5% / 6 months | 0–5% | <0% for 2 quarters |
| Win rate (portfolio) | >60% | 50–60% | <50% |
| Profit factor | >1.4 | 1.2–1.4 | <1.2 |
| TRAILING/PATTERN_TOP exit % | >45% | 35–45% | <35% |

**2. Identify underperforming stocks:**
```bash
# Look at per-stock P&L in backtest output
# Flag stocks with negative P&L for 2+ consecutive quarters
```

**3. Parameter drift check:**
- No parameter changes needed unless win rate drops below 55% or profit factor below 1.3
- If triggered, run recalibration (see below)

---

### Semi-Annual — Stock Screening (2 hours)

Run the full NSE screener to find better stock candidates:

```bash
# Pre-fetch takes ~12 min for ~2000 stocks at 3 req/sec
python scripts/screen.py --from <12-months-ago> --min-trades 3 --output screen_results_<date>.csv
```

**Candidate criteria:**
- `return_pct > 5%` over 6 months
- `win_rate >= 50%` (money-weighted)
- `total_trades >= 3`
- `avg_win / abs(avg_loss) > 1.5`
- NOT in T-group, BE segment, or with SEBI warnings
- Daily turnover > ₹50L (avoid illiquid stocks)

**How to add a candidate:**
1. Add to `config.yaml` watchlist
2. Pre-fetch its data manually (to avoid cache wipe):
   ```python
   python - <<'EOF'
   import sys; sys.path.insert(0, '.')
   from dotenv import load_dotenv; load_dotenv('config/.env')
   from trader.auth.session import create_kite
   from trader.data.store import Store
   from trader.data.historical import get_candles
   from trader.core.config import config
   from datetime import datetime

   kite = create_kite()
   store = Store(config.db_path)
   instruments = kite.instruments('NSE')
   sym_map = {f"NSE:{i['tradingsymbol']}": i['instrument_token'] for i in instruments}
   df = get_candles(kite, store, sym_map['NSE:NEWSYMBOL'], 'NSE:NEWSYMBOL', '15minute',
                    datetime(2020, 1, 1), datetime.now())
   print(f"Got {len(df)} candles")
   EOF
   ```
3. Run cache-only backtest and compare:
   ```bash
   python scripts/backtest.py --from 2020-01-01 --cache-only 2>/dev/null | tail -40
   ```
4. Accept if: total return improves AND per-stock return >8%/yr

**How to remove a stock:**
1. Remove from `config.yaml` watchlist
2. Run cache-only backtest to confirm overall return doesn't drop significantly
3. Close any open live position manually before removal

---

### Annual — Full Parameter Recalibration

Run calibration over the past 2 years of data to check if params have drifted:

```bash
python scripts/calibrate.py --from <2-years-ago> --mode random --iterations 200 --params threshold profit_pct trail_pct stop_pct sell_threshold sell_min_pct
```

**Params to calibrate (in priority order):**
1. `threshold` — most impactful: controls entry selectivity
2. `profit_pct` — trailing activation floor (don't go below 5%)
3. `trail_pct` — trailing distance (don't go above 3%)
4. `stop_pct` — hard SL (keep at 8-12%)
5. `sell_threshold` / `sell_min_pct` — pattern-top exit gate

**Hard constraints — do NOT change:**
- `atr_stop_mult`: keep 0.0 (ATR too small for 15min swing trades)
- `ema_gate_long_period`: keep 0 (dual-EMA hurts more than it helps)
- `model_stop_pct`: keep 0.0 (cuts profitable pullbacks)
- `hold_bars`: keep 400 (reducing causes MORE strategy exits, counterintuitively)

**Acceptance criteria for new params:**
- Must improve total return by >3% over 2-year window
- Must not increase max drawdown by >2%
- Must not reduce TRAILING exit % below 40%
- Validate on walk-forward before accepting:
  ```bash
  python scripts/walk_forward.py --from <2-years-ago> --train 6 --test 3
  ```
  - Accept only if walk-forward consistency >60%

---

## Red Flags Requiring Immediate Action

| Signal | Action |
|--------|--------|
| Monthly loss > 10% | Pause live trading; investigate which stocks are causing SL exits |
| 3 consecutive SL exits on same stock in 1 month | Remove stock from watchlist temporarily |
| Win rate drops below 50% over 3 months | Run parameter recalibration |
| TRAILING exit % drops below 35% | Stock rotation: remove STRATEGY-heavy stocks |
| Market-wide correction > 20% (Nifty) | Reduce `max_open_positions` to 6; raise `threshold` to 0.92 temporarily |

---

## Known Regime Behavior

| Market Regime | Expected Performance | How to Identify |
|---------------|---------------------|-----------------|
| Strong uptrend | TRAILING exits dominate; high profit factor | Nifty > 200-day MA; consistent monthly profits |
| Sideways/consolidation | STRATEGY exits increase; profit factor 1.2–1.5 | Monthly P&L erratic; STRATEGY exit % rises |
| Correction | SL exits spike initially, then TRAILING recovers | Nifty below 200-day MA; first 2 months painful |
| Panic/crash (like March 2020) | Heavy SL exits; daily loss limit may trigger | Nifty drops >5% in a week |

**In corrections:** The strategy recovers well because it buys dips. Don't panic-remove stocks purely on short-term performance. Give any regime change at least 2-3 months before acting.

---

## Stock-Specific Notes

| Stock | Strength | Watch for |
|-------|---------|-----------|
| CUPID | Best performer (+₹77.9k); micro-cap with high % moves | Volume drying up; SEBI category change |
| ANGELONE | Broker; benefits from bull market trading volumes | Regulatory changes to broking industry |
| IDFCFIRSTB | Small private bank; oscillates in rate cycles | NPA spikes; merger/acquisition news |
| IRCTC | Government monopoly; strong pre-correction; sideways in 2025 | Privatisation news; ticket pricing changes |
| ATHERENERG | EV infrastructure; high growth but volatile | Policy changes; promoter actions |
| CDSL | Depository; benefits from retail investor growth | NSDL competition; regulatory fee changes |
| BAJAJFINSV | NBFC holding co; mostly STRATEGY exits in 2025 | Bajaj Finance subsidiary performance |
| SBIN | PSU bank; good oscillation in rate cycles | NPA cycle; government disinvestment |
| NTPC | Utility; low efficiency (7.5%/yr) but steady | Renewable energy transition impact |
| INDUSINDBK | Private bank; volatile, similar to IDFCFIRSTB | MFI book stress; promoter stake |
| CHOLAFIN | NBFC; 4.8%/yr — marginal but contributes | NBFC credit stress cycles |
| GOKEX | Small cap; strong oscillation | Volume/liquidity changes |
| POLYCAB | Cables; benefits from infra spending | Competition; commodity price cycles |
| ASTRAL | Pipes; building materials cycle | Competition; real estate slowdown |

---

## What NOT to Change (Learned the Hard Way)

1. **ATR-based stops**: 15min bar ATR ≈ 0.5-1% of price. `atr_stop_mult=2.5` gives only ~1.5% stop — far too tight. Caused SL exits to jump from 83 to 106, TRAILING win rate dropped from 100% to 65%. Keep `atr_stop_mult=0.0`.

2. **Dual EMA gate** (`ema_gate_long_period`): EMA(200) filter blocked too many profitable trades. GOKEX halved, IDFCFIRSTB dropped from +₹10.7k to +₹1.1k in 2025. Keep `ema_gate_long_period=0`.

3. **Model stop** (`model_stop_pct`): Exits positions at small loss when model detects a top — but positions often recover to +7%+ gains. Dropped TRAILING count from 154 to 114. Keep `model_stop_pct=0.0`.

4. **Reducing hold_bars**: Setting `hold_bars=200` caused MORE STRATEGY exits (103 vs 65 at 400). Positions in bars 200-400 resolve naturally; cutting them early forces premature exits. Keep `hold_bars=400`.

5. **Lowering profit_pct below 7%**: At `profit_pct=4%`, trailing activates on noise bounces. GUJALKALI went from +₹8.5k to -₹20.6k. Keep `profit_pct=7`.

6. **Large-cap banking** (HDFCBANK): Too slow-moving. Generated -₹5.6k vs NTPC's +₹21.6k. Strategy needs oscillating mid-to-small caps.

---

## Implementation Checklist for Each Review

### Monthly checklist (5 min)
- [ ] Check last month's P&L from logs
- [ ] Note any stocks with all-SL or all-STRATEGY exits
- [ ] Flag for quarterly review if concerns

### Quarterly checklist (30 min)
- [ ] Run 6-month backtest (cache-only)
- [ ] Check per-stock performance table
- [ ] Identify underperformers (negative P&L for 2+ quarters)
- [ ] Check TRAILING exit % — should be >45%
- [ ] Replace one underperformer if found (pre-fetch data before adding)

### Semi-annual checklist (2 hours)
- [ ] Run screen.py against all NSE EQ stocks
- [ ] Review top candidates (return_pct >5%, win_rate >50%, ≥3 trades)
- [ ] Paper trade 2-3 candidates in `interested:` for 4 weeks
- [ ] Add best candidate to watchlist if it improves total return

### Annual checklist (half day)
- [ ] Run calibrate.py on key params (threshold, profit_pct, trail_pct)
- [ ] Run walk_forward.py to validate new params out-of-sample
- [ ] Update baseline section of this document with new numbers
