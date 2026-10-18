# Portfolio sim `SN-3_coin110` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹952,707 · trades 987 · win rate 51.6% · PF 1.38 · money-weighted win % 58.0 · avg ₹965/trade · max DD ₹566,765 (63.1%) · ann. return 10.1% · Calmar 0.16 · mean utilisation 97.0% · avg held 59.3 bars

## Excluding 2020

net ₹640,051 · trades 918 · win rate 50.4% · PF 1.28 · money-weighted win % 56.2 · avg ₹697/trade · max DD ₹368,832 (54.1%) · ann. return 7.3% · Calmar 0.14 · mean utilisation 97.0% · avg held 59.3 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -8,862 |
| TIME | 973 | 961,569 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 56 | -262,218 | 48.4 |
| 2012 | 64 | 211,511 | 28.8 |
| 2013 | 60 | -195,825 | 53.4 |
| 2014 | 60 | 295,710 | 19.6 |
| 2015 | 60 | 13,052 | 16.6 |
| 2016 | 60 | 75,663 | 22.4 |
| 2017 | 60 | 113,005 | 7.6 |
| 2018 | 61 | -185,760 | 29.8 |
| 2019 | 65 | -112,216 | 26.5 |
| 2020 | 69 | 312,656 | 44.4 |
| 2021 | 60 | 234,152 | 6.5 |
| 2022 | 60 | 55,778 | 11.4 |
| 2023 | 60 | 155,147 | 4.5 |
| 2024 | 60 | 227,053 | 4.8 |
| 2025 | 60 | 11,418 | 7.2 |
| 2026 | 72 | 3,580 | 6.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 6; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin110",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:110",
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
