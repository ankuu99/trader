# Portfolio sim `SC2-d40_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,231,494 · trades 1461 · win rate 53.1% · PF 1.44 · money-weighted win % 59.1 · avg ₹843/trade · max DD ₹384,505 (40.8%) · ann. return 13.0% · Calmar 0.32 · mean utilisation 95.5% · avg held 39.8 bars

## Excluding 2020

net ₹1,070,738 · trades 1366 · win rate 52.2% · PF 1.42 · money-weighted win % 58.6 · avg ₹784/trade · max DD ₹285,220 (40.8%) · ann. return 12.3% · Calmar 0.30 · mean utilisation 95.5% · avg held 39.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -19,914 |
| TIME | 1446 | 1,251,408 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 80 | -140,456 | 40.8 |
| 2012 | 94 | 158,212 | 14.4 |
| 2013 | 93 | -22,083 | 37.9 |
| 2014 | 91 | 276,069 | 6.9 |
| 2015 | 92 | 37,395 | 10.9 |
| 2016 | 90 | 70,803 | 12.0 |
| 2017 | 91 | 274,308 | 12.2 |
| 2018 | 93 | 4,952 | 14.0 |
| 2019 | 92 | -81,282 | 14.7 |
| 2020 | 95 | 160,756 | 20.1 |
| 2021 | 94 | 173,008 | 4.3 |
| 2022 | 91 | -12,872 | 9.5 |
| 2023 | 91 | 119,932 | 7.2 |
| 2024 | 93 | 44,427 | 7.0 |
| 2025 | 94 | 176,787 | 2.9 |
| 2026 | 87 | -8,462 | 3.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 11; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d40_prod",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 40,
  "score_source": "ref:prod_pmin",
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
  "queue_max_runup": null
}
```
