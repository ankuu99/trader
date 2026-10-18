# Portfolio sim `SC1-1a_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹264,678 · trades 1162 · win rate 51.4% · PF 1.07 · money-weighted win % 51.8 · avg ₹228/trade · max DD ₹672,367 (53.6%) · ann. return 2.8% · Calmar 0.05 · mean utilisation 74.6% · avg held 19.9 bars

## Excluding 2020

net ₹341,160 · trades 1107 · win rate 51.2% · PF 1.10 · money-weighted win % 52.4 · avg ₹308/trade · max DD ₹640,077 (51.1%) · ann. return 3.9% · Calmar 0.08 · mean utilisation 74.6% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 7 | -25,228 |
| TIME | 1155 | 289,906 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 49 | -158,044 | 28.5 |
| 2012 | 81 | 200,771 | 18.5 |
| 2013 | 73 | 48,542 | 29.5 |
| 2014 | 81 | 222,519 | 7.6 |
| 2015 | 75 | 60,553 | 5.9 |
| 2016 | 73 | -68,701 | 16.1 |
| 2017 | 71 | 157,464 | 25.9 |
| 2018 | 75 | -147,167 | 19.7 |
| 2019 | 74 | -100,956 | 27.2 |
| 2020 | 55 | -76,481 | 30.4 |
| 2021 | 84 | 33,483 | 14.2 |
| 2022 | 70 | -75,824 | 20.7 |
| 2023 | 79 | 114,130 | 17.5 |
| 2024 | 81 | 18,784 | 11.9 |
| 2025 | 70 | 45,707 | 5.5 |
| 2026 | 71 | -10,100 | 9.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-1a_prod",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 80000,
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
