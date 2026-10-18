# Portfolio sim `SC1-1b_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹559,045 · trades 764 · win rate 52.9% · PF 1.15 · money-weighted win % 53.4 · avg ₹732/trade · max DD ₹487,411 (67.8%) · ann. return 5.9% · Calmar 0.09 · mean utilisation 73.8% · avg held 20.0 bars

## Excluding 2020

net ₹597,611 · trades 728 · win rate 52.7% · PF 1.17 · money-weighted win % 53.9 · avg ₹821/trade · max DD ₹469,414 (67.8%) · ann. return 6.9% · Calmar 0.10 · mean utilisation 73.8% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 5 | -24,901 |
| TIME | 759 | 583,946 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 27 | -104,971 | 33.8 |
| 2012 | 42 | 137,356 | 17.3 |
| 2013 | 48 | -204,059 | 65.9 |
| 2014 | 51 | 267,481 | 11.6 |
| 2015 | 52 | 59,703 | 16.3 |
| 2016 | 51 | 165,858 | 14.3 |
| 2017 | 52 | 53,609 | 12.4 |
| 2018 | 50 | -245,781 | 36.2 |
| 2019 | 47 | 43,069 | 24.0 |
| 2020 | 36 | -38,566 | 37.6 |
| 2021 | 57 | 129,691 | 11.3 |
| 2022 | 45 | -65,415 | 18.4 |
| 2023 | 54 | 175,555 | 13.8 |
| 2024 | 51 | 115,687 | 10.5 |
| 2025 | 52 | -27,657 | 6.6 |
| 2026 | 49 | 97,485 | 6.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 1; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-1b_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "run",
  "capital": 600000,
  "slot": 120000,
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
