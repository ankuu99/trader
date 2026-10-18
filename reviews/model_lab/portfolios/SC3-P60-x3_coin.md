# Portfolio sim `SC3-P60-x3_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,150,333 · trades 1103 · win rate 55.5% · PF 1.50 · money-weighted win % 60.0 · avg ₹1,043/trade · max DD ₹491,300 (47.3%) · ann. return 12.1% · Calmar 0.26 · mean utilisation 96.8% · avg held 52.7 bars

## Excluding 2020

net ₹1,012,736 · trades 1027 · win rate 55.5% · PF 1.50 · money-weighted win % 59.9 · avg ₹986/trade · max DD ₹326,195 (47.3%) · ann. return 11.6% · Calmar 0.25 · mean utilisation 96.8% · avg held 53.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -27,832 |
| TIME | 789 | 144,214 |
| TRAIL | 299 | 1,033,951 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 59 | -132,660 | 39.8 |
| 2012 | 67 | 31,547 | 21.3 |
| 2013 | 75 | -23,729 | 41.8 |
| 2014 | 70 | 311,990 | 7.8 |
| 2015 | 71 | 29,895 | 13.6 |
| 2016 | 68 | 123,366 | 12.4 |
| 2017 | 70 | 150,456 | 7.2 |
| 2018 | 71 | -38,607 | 16.2 |
| 2019 | 69 | -99,361 | 20.5 |
| 2020 | 76 | 137,597 | 30.8 |
| 2021 | 68 | 304,946 | 5.0 |
| 2022 | 72 | 13,320 | 11.4 |
| 2023 | 65 | 132,949 | 4.5 |
| 2024 | 68 | 190,387 | 4.8 |
| 2025 | 66 | 46,416 | 4.3 |
| 2026 | 68 | -28,179 | 5.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 6; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x3_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": 0.1,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
