# Portfolio sim `SC2-d5_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹-138,607 · trades 7480 · win rate 47.4% · PF 0.98 · money-weighted win % 49.4 · avg ₹-19/trade · max DD ₹505,721 (80.9%) · ann. return -1.5% · Calmar -0.02 · mean utilisation 50.5% · avg held 5.0 bars

## Excluding 2020

net ₹-123,275 · trades 6997 · win rate 47.5% · PF 0.98 · money-weighted win % 49.4 · avg ₹-18/trade · max DD ₹334,034 (55.0%) · ann. return -1.4% · Calmar -0.03 · mean utilisation 50.5% · avg held 5.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 8 | -1,772 |
| TIME | 7472 | -136,835 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 461 | -180,976 | 31.2 |
| 2012 | 487 | -8,700 | 31.1 |
| 2013 | 480 | -52,591 | 36.2 |
| 2014 | 463 | 51,996 | 14.4 |
| 2015 | 478 | -44,036 | 25.8 |
| 2016 | 471 | -14,237 | 25.7 |
| 2017 | 474 | 66,745 | 36.3 |
| 2018 | 469 | -21,912 | 25.7 |
| 2019 | 464 | -69,438 | 31.0 |
| 2020 | 483 | -15,332 | 65.8 |
| 2021 | 465 | 82,866 | 15.1 |
| 2022 | 470 | -49,530 | 30.3 |
| 2023 | 475 | 138,482 | 7.4 |
| 2024 | 475 | 77,971 | 11.4 |
| 2025 | 479 | -38,846 | 14.3 |
| 2026 | 386 | -61,068 | 14.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 32; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d5_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 5,
  "score_source": "ref:coin",
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
