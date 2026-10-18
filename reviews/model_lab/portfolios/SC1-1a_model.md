# Portfolio sim `SC1-1a_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹385,485 · trades 1033 · win rate 52.2% · PF 1.11 · money-weighted win % 52.6 · avg ₹373/trade · max DD ₹370,250 (55.0%) · ann. return 4.1% · Calmar 0.07 · mean utilisation 66.3% · avg held 19.9 bars

## Excluding 2020

net ₹481,391 · trades 986 · win rate 52.2% · PF 1.15 · money-weighted win % 53.5 · avg ₹488/trade · max DD ₹370,250 (55.0%) · ann. return 5.5% · Calmar 0.10 · mean utilisation 66.3% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 6 | -29,921 |
| TIME | 1027 | 415,405 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 37 | -121,555 | 28.9 |
| 2012 | 55 | 161,692 | 15.7 |
| 2013 | 66 | -151,379 | 55.0 |
| 2014 | 68 | 142,208 | 11.7 |
| 2015 | 74 | -18,181 | 18.9 |
| 2016 | 69 | 91,346 | 19.5 |
| 2017 | 70 | 11,301 | 15.8 |
| 2018 | 70 | -145,861 | 36.1 |
| 2019 | 61 | 143,543 | 30.5 |
| 2020 | 47 | -95,906 | 43.1 |
| 2021 | 76 | 125,645 | 10.5 |
| 2022 | 59 | -35,781 | 17.0 |
| 2023 | 75 | 167,300 | 9.7 |
| 2024 | 69 | 104,319 | 8.2 |
| 2025 | 71 | -13,986 | 7.2 |
| 2026 | 66 | 20,779 | 6.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 2; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-1a_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "run",
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
