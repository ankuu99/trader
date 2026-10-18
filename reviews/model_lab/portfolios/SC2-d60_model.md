# Portfolio sim `SC2-d60_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹431,386 · trades 976 · win rate 51.6% · PF 1.17 · money-weighted win % 53.9 · avg ₹442/trade · max DD ₹560,214 (70.4%) · ann. return 4.6% · Calmar 0.06 · mean utilisation 96.5% · avg held 59.6 bars

## Excluding 2020

net ₹393,554 · trades 914 · win rate 51.3% · PF 1.17 · money-weighted win % 53.9 · avg ₹431/trade · max DD ₹384,965 (59.5%) · ann. return 4.5% · Calmar 0.08 · mean utilisation 96.5% · avg held 59.6 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -33,509 |
| TIME | 961 | 464,894 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 49 | -186,954 | 45.4 |
| 2012 | 63 | 99,234 | 25.2 |
| 2013 | 64 | -78,523 | 54.5 |
| 2014 | 60 | 116,578 | 15.1 |
| 2015 | 64 | -63,669 | 27.9 |
| 2016 | 60 | 98,181 | 21.0 |
| 2017 | 60 | 152,680 | 11.7 |
| 2018 | 60 | -161,131 | 31.5 |
| 2019 | 60 | -97,918 | 31.2 |
| 2020 | 62 | 37,831 | 54.8 |
| 2021 | 64 | 303,437 | 8.5 |
| 2022 | 63 | -52,903 | 22.6 |
| 2023 | 61 | 127,368 | 10.5 |
| 2024 | 62 | 103,951 | 7.0 |
| 2025 | 63 | 96,512 | 7.4 |
| 2026 | 61 | -63,289 | 9.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 11; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d60_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "run",
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
