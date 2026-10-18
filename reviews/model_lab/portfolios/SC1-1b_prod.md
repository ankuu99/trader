# Portfolio sim `SC1-1b_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹287,336 · trades 855 · win rate 51.2% · PF 1.07 · money-weighted win % 51.7 · avg ₹336/trade · max DD ₹809,095 (64.0%) · ann. return 3.0% · Calmar 0.05 · mean utilisation 82.6% · avg held 19.9 bars

## Excluding 2020

net ₹371,783 · trades 814 · win rate 51.1% · PF 1.09 · money-weighted win % 52.3 · avg ₹457/trade · max DD ₹796,475 (63.0%) · ann. return 4.3% · Calmar 0.07 · mean utilisation 82.6% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 5 | -31,572 |
| TIME | 850 | 318,908 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 37 | -201,794 | 35.1 |
| 2012 | 57 | 251,961 | 27.6 |
| 2013 | 53 | -76,974 | 50.4 |
| 2014 | 59 | 209,964 | 9.7 |
| 2015 | 56 | 58,397 | 8.3 |
| 2016 | 54 | -72,589 | 22.3 |
| 2017 | 53 | 211,903 | 38.4 |
| 2018 | 56 | -206,262 | 27.0 |
| 2019 | 54 | -105,037 | 40.4 |
| 2020 | 41 | -84,447 | 35.9 |
| 2021 | 61 | 104,043 | 15.7 |
| 2022 | 53 | -118,392 | 28.2 |
| 2023 | 58 | 233,692 | 24.2 |
| 2024 | 59 | 21,223 | 13.6 |
| 2025 | 53 | 31,702 | 7.4 |
| 2026 | 51 | 29,945 | 9.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-1b_prod",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:prod_pmin",
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
