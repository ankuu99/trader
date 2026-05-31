# Support/Resistance Logic — Implementation Plan

## Evaluation

**Does it make sense?**

Yes, strongly. The current strategy has a fundamental gap: it detects *local* minima/maxima using LR on recent candles, but has no concept of whether that dip is *meaningful* — i.e., whether price is bouncing off a level that has historically held. A random local minimum in the middle of a range is very different from a local minimum touching a 6-month support zone.

**Current gaps this addresses:**

| Problem | S/R fix |
|---|---|
| LR entry fires on weak dips with no historical significance | Gate entry: only enter if dip is near a support cluster |
| Pattern-top exit uses a fixed % gain floor (`sell_min_pct`) | Replace/supplement: exit when near a known resistance level, regardless of % gain |
| Trailing stop is symmetric — doesn't know if price is about to hit a ceiling | Tighten trail when approaching resistance |

---

## What the research says

- **Osler (2000, 2003)** — *"Support for Resistance: Technical Analysis and Intraday Exchange Rates"* (Journal of Finance) — found statistically significant clustering of order flow around round-number S/R levels in FX.
- **Lo, Mamaysky, Wang (2000)** — *"Foundations of Technical Analysis"* (Journal of Finance) — showed pivot-based patterns have statistically non-random properties on US equities; informational content exists even after transaction costs.
- **Brock, Lakonishok, LeBaron (1992)** — showed simple technical rules outperform buy-and-hold on DJIA 1897–1986, including S/R-derived rules.
- Recent ML work (2020–2024) uses S/R proximity as features in tree-based models and LSTMs for entry timing — consistent finding is that proximity to a tested level improves signal quality over raw price-pattern detection alone.

The consensus: S/R levels correlate with actual order clustering and regime boundaries. The effect is strongest when a level has been tested multiple times (2+ touches).

---

## Core Concept

**Support** = cluster of historical local minima within a tolerance band, held 2+ times.
**Resistance** = cluster of historical local maxima within a tolerance band, rejected 2+ times.

The strategy already finds local extrema for training — S/R detection reuses that logic over a longer lookback.

---

## Phase 1 — S/R Detection (new internal method)

```python
_compute_sr_levels(candles, lookback, tolerance_pct, min_touches)
→ returns: support_levels: list[float], resistance_levels: list[float]
```

Algorithm:
1. Find all local minima and maxima in the last `sr_lookback_bars` candles (reuse `_find_local_extrema`)
2. Cluster nearby minima: merge any two minima within `sr_tolerance_pct`% of each other into one level (use their mean price), count touches
3. Keep only clusters with `>= sr_min_touches`
4. Same for maxima → resistance levels

New config params:

| Param | Default | Meaning |
|---|---|---|
| `sr_lookback_bars` | 150 | Bars to scan for S/R levels |
| `sr_tolerance_pct` | 1.0 | % band to merge nearby pivots into one level |
| `sr_min_touches` | 2 | Minimum pivot touches to call a level "significant" |

---

## Phase 2 — Entry Gate (support proximity)

New optional gate in the existing entry gate block:

```yaml
sr_entry_gate_enabled: false   # off by default
sr_entry_proximity_pct: 1.5    # entry must be within 1.5% above a support level
```

Gate logic:
- Compute S/R levels
- Find nearest support below current price
- Block entry if `(current_price - support) / support * 100 > sr_entry_proximity_pct`

This means: LR says "looks like a local min" AND price is actually near a historically tested floor. Both must agree.

---

## Phase 3 — Exit Enhancement (resistance proximity)

Two options — both configurable, not mutually exclusive:

### Option A — Dynamic trail tightening near resistance (recommended first)

```yaml
sr_exit_tighten_enabled: false
sr_exit_proximity_pct: 1.5     # tighten trail when within 1.5% below resistance
sr_exit_tight_trail_pct: 0.3   # use this trail_pct when near resistance
```

When trailing is active and price is within `sr_exit_proximity_pct`% below a resistance level, temporarily use `sr_exit_tight_trail_pct` instead of `trail_pct`. Captures most of the move before the likely rejection.

### Option B — Direct resistance exit

```yaml
sr_exit_at_resistance: false
sr_exit_resistance_pct: 1.0    # exit if price is within 1.0% below resistance AND profitable
```

Emit EXIT signal immediately when price is near resistance, bypassing the `sell_min_pct` gate. More aggressive — replaces pattern-top percentage floor with a structural level.

**Recommendation:** Implement Option A first (less disruptive, supplements existing trailing), then test Option B.

---

## Phase 4 (Optional) — S/R as LR Features

Add two more features to `_compute_features`:
- `support_distance_pct` — how far current price is above nearest support (as %)
- `resistance_distance_pct` — how far current price is below nearest resistance (as %)

This lets the LR model *learn* the relationship between S/R proximity and local extrema quality, rather than using it as a hard gate. More flexible but harder to interpret.

**Defer to Phase 4** — gates (Phases 2+3) are testable via backtest without changing the model training pipeline.

---

## Integration Notes

- All new params default to `false`/`0` — fully backward compatible, existing behavior unchanged unless explicitly enabled
- Can A/B test via calibration by adding new params to the search space
- Implementation lives in `trader/strategies/lr_extrema.py`

---

## Testing Approach

Start with Phase 1 + Phase 2 (entry gate only). Run calibration comparing:
- Baseline: `sr_entry_gate_enabled: false`
- Test: `sr_entry_gate_enabled: true`, `sr_min_touches: 2`, varying `sr_entry_proximity_pct` (1.0, 1.5, 2.0)

**Hypothesis:** win rate improves, total trades drop. If win rate goes up +10pp with trade count dropping <30%, that is a net positive.
