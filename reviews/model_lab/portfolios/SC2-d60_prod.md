# Portfolio sim `SC2-d60_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,153,685 · trades 976 · win rate 53.2% · PF 1.50 · money-weighted win % 60.1 · avg ₹1,182/trade · max DD ₹368,100 (31.3%) · ann. return 12.2% · Calmar 0.39 · mean utilisation 96.6% · avg held 59.7 bars

## Excluding 2020

net ₹1,050,746 · trades 914 · win rate 52.7% · PF 1.51 · money-weighted win % 60.1 · avg ₹1,150/trade · max DD ₹273,120 (31.3%) · ann. return 12.1% · Calmar 0.38 · mean utilisation 96.6% · avg held 59.7 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -34,559 |
| TIME | 961 | 1,188,243 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 51 | -118,811 | 31.3 |
| 2012 | 65 | 102,738 | 19.9 |
| 2013 | 64 | 36,821 | 23.6 |
| 2014 | 60 | 162,858 | 7.0 |
| 2015 | 60 | 5,890 | 13.7 |
| 2016 | 60 | 80,232 | 13.1 |
| 2017 | 60 | 273,209 | 15.0 |
| 2018 | 60 | -95,750 | 15.1 |
| 2019 | 60 | -95,857 | 15.1 |
| 2020 | 62 | 102,938 | 23.0 |
| 2021 | 64 | 333,389 | 4.8 |
| 2022 | 66 | -23,735 | 11.7 |
| 2023 | 62 | 177,062 | 5.3 |
| 2024 | 61 | 87,217 | 5.9 |
| 2025 | 60 | 191,942 | 4.6 |
| 2026 | 61 | -66,459 | 4.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 8; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d60_prod",
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
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
