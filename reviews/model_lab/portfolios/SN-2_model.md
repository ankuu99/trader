# Portfolio sim `SN-2_model` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹706,865 · trades 1139 · win rate 55.8% · PF 1.27 · money-weighted win % 55.9 · avg ₹621/trade · max DD ₹307,681 (42.3%) · ann. return 7.5% · Calmar 0.18 · mean utilisation 96.5% · avg held 51.3 bars

## Excluding 2020

net ₹646,436 · trades 1060 · win rate 54.9% · PF 1.27 · money-weighted win % 55.9 · avg ₹610/trade · max DD ₹280,911 (42.3%) · ann. return 7.4% · Calmar 0.18 · mean utilisation 96.5% · avg held 51.7 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | 3,357 |
| END | 15 | -23,902 |
| TARGET | 324 | 2,563,081 |
| TIME | 799 | -1,835,672 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 58 | -113,627 | 32.8 |
| 2012 | 80 | 146,604 | 15.0 |
| 2013 | 76 | -63,465 | 42.3 |
| 2014 | 75 | 137,053 | 14.4 |
| 2015 | 66 | -62,365 | 18.5 |
| 2016 | 70 | 85,564 | 15.2 |
| 2017 | 75 | 153,875 | 5.2 |
| 2018 | 75 | -37,811 | 18.8 |
| 2019 | 71 | 1,631 | 15.3 |
| 2020 | 79 | 60,428 | 30.7 |
| 2021 | 75 | 200,274 | 5.8 |
| 2022 | 64 | -67,505 | 14.3 |
| 2023 | 72 | 114,474 | 11.8 |
| 2024 | 69 | 118,903 | 5.7 |
| 2025 | 66 | 20,973 | 7.5 |
| 2026 | 68 | 11,857 | 4.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 2; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_model",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": 0.2,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null,
  "sources": [],
  "delist_grace_days": 7
}
```
