# Portfolio sim `SN-2_coin106` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹716,381 · trades 1155 · win rate 55.3% · PF 1.25 · money-weighted win % 55.6 · avg ₹620/trade · max DD ₹472,175 (43.2%) · ann. return 7.6% · Calmar 0.18 · mean utilisation 96.7% · avg held 50.7 bars

## Excluding 2020

net ₹652,675 · trades 1070 · win rate 54.5% · PF 1.26 · money-weighted win % 55.7 · avg ₹610/trade · max DD ₹272,444 (38.5%) · ann. return 7.5% · Calmar 0.19 · mean utilisation 96.7% · avg held 51.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | -2,496 |
| END | 15 | -22,440 |
| TARGET | 355 | 2,794,734 |
| TIME | 784 | -2,053,417 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 61 | -162,274 | 38.4 |
| 2012 | 77 | 193,363 | 16.0 |
| 2013 | 75 | -25,129 | 37.1 |
| 2014 | 84 | 288,655 | 9.3 |
| 2015 | 67 | -42,920 | 12.8 |
| 2016 | 71 | 33,603 | 15.0 |
| 2017 | 74 | 194,984 | 4.0 |
| 2018 | 69 | -132,647 | 21.5 |
| 2019 | 66 | -74,037 | 15.7 |
| 2020 | 85 | 63,706 | 31.3 |
| 2021 | 73 | 144,488 | 5.6 |
| 2022 | 70 | -22,685 | 12.9 |
| 2023 | 71 | 108,882 | 7.1 |
| 2024 | 72 | 216,242 | 6.3 |
| 2025 | 69 | -39,425 | 8.3 |
| 2026 | 71 | -28,426 | 6.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin106",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:106",
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
