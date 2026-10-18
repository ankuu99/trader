# Portfolio sim `SC3-P60-x4_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,294,148 · trades 1056 · win rate 52.1% · PF 1.59 · money-weighted win % 61.4 · avg ₹1,226/trade · max DD ₹317,632 (31.2%) · ann. return 13.7% · Calmar 0.44 · mean utilisation 96.6% · avg held 55.0 bars

## Excluding 2020

net ₹1,202,100 · trades 986 · win rate 52.1% · PF 1.60 · money-weighted win % 61.6 · avg ₹1,219/trade · max DD ₹228,672 (31.2%) · ann. return 13.8% · Calmar 0.44 · mean utilisation 96.6% · avg held 55.1 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -16,809 |
| TIME | 847 | 630,402 |
| TRAIL | 194 | 680,555 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 57 | -103,104 | 28.8 |
| 2012 | 66 | 142,531 | 18.0 |
| 2013 | 68 | -41,224 | 31.2 |
| 2014 | 69 | 220,162 | 9.8 |
| 2015 | 63 | 32,532 | 12.8 |
| 2016 | 62 | 65,255 | 8.7 |
| 2017 | 69 | 570,359 | 13.1 |
| 2018 | 71 | -121,177 | 11.9 |
| 2019 | 67 | 59,510 | 10.2 |
| 2020 | 70 | 92,048 | 18.0 |
| 2021 | 66 | 223,621 | 4.0 |
| 2022 | 67 | 36,085 | 7.6 |
| 2023 | 62 | 56,579 | 7.1 |
| 2024 | 65 | 83,629 | 5.5 |
| 2025 | 68 | 71,512 | 5.0 |
| 2026 | 66 | -94,169 | 5.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 9; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x4_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": 0.15,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
