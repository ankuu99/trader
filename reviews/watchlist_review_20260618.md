# Watchlist Review — 2026-06-18

## Portfolio Summary
| Metric | Value |
|--------|-------|
| Full period P&L (2023-01-01→) | ₹13,84,354 |
| Return | 553.7% |
| Trades | 1651 |
| Win rate | 55.4% |
| Max drawdown | ₹55,577 |
| Recent 6m P&L | ₹40,841 |
| Stocks profitable (recent 6m) | 13/19 |

**Headline:** the deterministic trend guard caught three falling knives the backtest rated as
winners — the regime-blindness this review exists to catch. AQYLON in particular is a rebranded
story-stock whose ₹2L backtest profit is a pump-era artifact.

## Recommendations

### ✅ KEEP
| Stock | Full P&L | Recent P&L | Trend | WR | Guard | Gate | News |
|-------|----------|------------|-------|----|-------|------|------|
| NSE:MARKSANS | ₹75,174 | ₹11,607 | stable | 58% | RANGE_BOUND | — | Clean; best recent performer |
| NSE:ASHOKLEY | ₹51,512 | ₹7,578 | stable | 58% | RANGE_BOUND | — | Clean |
| NSE:GUJALKALI | ₹18,279 | ₹1,641 | stable | 61% | RANGE_BOUND | — | Clean (sparse recent trades) |
| NSE:LTF | ₹43,813 | ₹3,848 | stable | 51% | UPTREND | — | Keep, but uptrend = fewer minima |

### 👀 WATCH
| Stock | Full P&L | Recent P&L | Trend | WR | Guard | Gate | Concern |
|-------|----------|------------|-------|----|-------|------|---------|
| NSE:RECLTD | ₹22,134 | ₹2,813 | stable | 59% | **DOWNTREND** | WATCH | **Quant↔guard disagreement.** REC merging into PFC (MoP approved 10-Jun-2026); ₹645→₹348. Business healthy (GNPA 1.06%) but the entity is changing — event risk. |
| NSE:INDHOTEL | ₹32,662 | ₹1,546 | declining | 47% | RANGE_BOUND | WATCH | AGM ~30-Jun event window (per prior re-check); re-qualify after. |
| NSE:M&MFIN | ₹40,659 | ₹280 | declining | 46% | RANGE_BOUND | — | dd −26%, 6m −14.3% — softening but structurally intact. |
| NSE:CUPID | ₹92,767 | ₹4,763 | declining | 56% | UPTREND | — | Strong uptrend → few local minima; profit is trend-regime dependent. |
| NSE:DIACABS | ₹1,44,398 | ₹5,229 | declining | 54% | UPTREND | — | Same uptrend caveat. |
| NSE:SKYGOLD | ₹1,16,385 | ₹1,185 | declining | 59% | UPTREND | — | Same uptrend caveat. |

### 🔧 CALIBRATE
| Stock | Full P&L | Recent P&L | Trend | WR | Guard | Gate | Action |
|-------|----------|------------|-------|----|-------|------|--------|
| NSE:CGPOWER | ₹78,017 | −₹2,638 | declining | 54% | RANGE_BOUND | — | Recent WR 20% — recalibrate; structurally fine. |
| NSE:TVSMOTOR | ₹5 | −₹1,732 | declining | 57% | RANGE_BOUND | — | Barely traded full-period; recalibrate or drop. |
| NSE:NATIONALUM | ₹53,571 | −₹1,149 | declining | 52% | UPTREND | — | Recalibrate; uptrend fit caveat. |
| NSE:HAL | ₹6,302 | ₹0 | declining | 46% | RANGE_BOUND | — | 0 signals in 6m + forward-label filter too strict — recalibrate. |
| NSE:ATHERENERG | ₹45,034 | −₹1,138 | declining | 66% | UPTREND | — | Sparse recent (4 trades); uptrend. |

### ❌ REMOVE
| Stock | Full P&L | Recent P&L | Trend | Guard | Gate | Reason |
|-------|----------|------------|-------|-------|------|--------|
| NSE:AQYLON | ₹2,04,817 | ₹3,704 | declining | **FALLING_KNIFE** | **AVOID** | Aqylon Nexus = **renamed Sri Adhikari Brothers TV (Jan 2026)** into "AI/space/semiconductor" story stock. ₹224→₹39 (−83%). Pump-and-dump pattern; ₹2L backtest is a pump-era artifact. Highest-conviction removal. |
| NSE:RMDRIP | ₹1,58,577 | ₹856 | declining | **FALLING_KNIFE** | **AVOID** | Secular collapse −72.7% from peak (6m −57.9%); every dip a false bottom. Already diagnosed prior session. |
| NSE:TARAPUR | ₹2,00,571 | −₹3,168 | declining | **FALLING_KNIFE** | AVOID | Thin microcap transformer maker, dd −59.8%; quant + guard agree. Illiquid + structurally declining. |
| NSE:RADICO* | −₹321 | ₹5,617 | improving | RANGE_BOUND | — | *NOT a real remove — quant rule flagged it on full.pnl −₹321, but recent is +₹5,617 and improving, guard clean. Reclassify → KEEP/WATCH. (Rule artifact, noted.) |

## Key cross-checks
- **3 falling knives** (AQYLON, RMDRIP, TARAPUR) were all backtest "winners" (₹1.6L–₹2L each) — the exact regime trap. Combined they carry large historical P&L that won't repeat.
- **6 names in strong UPTRENDs** (ATHERENERG, CUPID, NATIONALUM, LTF, SKYGOLD, DIACABS): not loss risks today, but their edge is trend-regime-dependent — if they roll over they become the next RMDRIP. Portfolio concentration risk worth monitoring.
- **RADICO** exposes a bug in the Step-2 rule (REMOVE on full.pnl<0 ignores a strongly improving recent) — treat as KEEP/WATCH, and consider fixing the classifier rule.

## Suggested Actions
- [ ] **Remove**: AQYLON, RMDRIP, TARAPUR (falling knives; AQYLON also a story-stock red flag)
- [ ] **Escalate to WATCH / re-qualify**: RECLTD (PFC merger event), INDHOTEL (post-AGM 30-Jun)
- [ ] **Calibrate**: CGPOWER, TVSMOTOR, NATIONALUM, HAL, ATHERENERG
- [ ] **Reclassify**: RADICO → KEEP (rule artifact); consider fixing the Step-2 REMOVE rule
- [ ] **Monitor**: the 6 uptrend names for trend exhaustion
