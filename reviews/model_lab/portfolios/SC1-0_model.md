# Portfolio sim `SC1-0_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹728,451 · trades 1934 · win rate 53.6% · PF 1.24 · money-weighted win % 55.4 · avg ₹377/trade · max DD ₹325,933 (34.2%) · ann. return 7.7% · Calmar 0.22 · mean utilisation 61.7% · avg held 19.9 bars

## Excluding 2020

net ₹874,768 · trades 1839 · win rate 53.7% · PF 1.33 · money-weighted win % 57.1 · avg ₹476/trade · max DD ₹254,014 (34.2%) · ann. return 10.0% · Calmar 0.29 · mean utilisation 61.7% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -6,006 |
| TIME | 1920 | 734,458 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 77 | -31,783 | 17.9 |
| 2012 | 103 | 169,778 | 15.4 |
| 2013 | 118 | -89,568 | 34.2 |
| 2014 | 124 | 191,253 | 5.1 |
| 2015 | 128 | -48,672 | 14.3 |
| 2016 | 139 | 81,974 | 14.7 |
| 2017 | 128 | 85,920 | 5.8 |
| 2018 | 129 | -50,871 | 13.5 |
| 2019 | 107 | 111,539 | 15.9 |
| 2020 | 95 | -146,316 | 30.6 |
| 2021 | 141 | 140,055 | 7.4 |
| 2022 | 113 | 28,061 | 8.0 |
| 2023 | 143 | 159,199 | 5.6 |
| 2024 | 130 | 76,251 | 5.8 |
| 2025 | 126 | 20,622 | 4.9 |
| 2026 | 133 | 31,008 | 7.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 18; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-0_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "run",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
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
