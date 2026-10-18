# Portfolio sim `SN-4_coin108` (run `A07n_dayn_hgbq_mfe20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹266,285 · trades 2935 · win rate 48.9% · PF 1.06 · money-weighted win % 51.4 · avg ₹91/trade · max DD ₹606,465 (100.9%) · ann. return 2.8% · Calmar 0.03 · mean utilisation 93.7% · avg held 19.9 bars

## Excluding 2020

net ₹85,907 · trades 2743 · win rate 48.5% · PF 1.02 · money-weighted win % 50.5 · avg ₹31/trade · max DD ₹453,155 (75.4%) · ann. return 1.0% · Calmar 0.01 · mean utilisation 93.7% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 3 | -1,916 |
| END | 14 | -4,983 |
| TIME | 2918 | 273,184 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 175 | -231,318 | 45.1 |
| 2012 | 185 | 72,140 | 26.8 |
| 2013 | 189 | -132,069 | 67.8 |
| 2014 | 184 | 171,789 | 21.8 |
| 2015 | 183 | -157,952 | 46.6 |
| 2016 | 186 | -10,186 | 43.7 |
| 2017 | 188 | 100,207 | 19.3 |
| 2018 | 182 | -63,511 | 43.4 |
| 2019 | 182 | -117,019 | 51.5 |
| 2020 | 192 | 180,378 | 102.0 |
| 2021 | 184 | 198,594 | 10.3 |
| 2022 | 186 | -18,122 | 22.3 |
| 2023 | 185 | 183,238 | 7.8 |
| 2024 | 184 | 108,144 | 10.2 |
| 2025 | 189 | -13,690 | 13.8 |
| 2026 | 161 | -4,338 | 12.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 14; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-4_coin108",
  "run_id": "A07n_dayn_hgbq_mfe20",
  "hold_bars": 20,
  "score_source": "coin:108",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null,
  "sources": [],
  "delist_grace_days": 7
}
```
