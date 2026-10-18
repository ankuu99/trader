# Portfolio sim `SN-3_coin102` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,028,490 · trades 986 · win rate 49.7% · PF 1.41 · money-weighted win % 58.5 · avg ₹1,043/trade · max DD ₹429,523 (44.8%) · ann. return 10.9% · Calmar 0.24 · mean utilisation 96.8% · avg held 59.4 bars

## Excluding 2020

net ₹686,495 · trades 917 · win rate 48.2% · PF 1.30 · money-weighted win % 56.6 · avg ₹749/trade · max DD ₹336,050 (44.8%) · ann. return 7.9% · Calmar 0.18 · mean utilisation 96.8% · avg held 59.3 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | -6,489 |
| END | 14 | 2,197 |
| TIME | 971 | 1,032,783 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 55 | -201,336 | 36.6 |
| 2012 | 65 | 168,557 | 25.2 |
| 2013 | 60 | -101,810 | 42.3 |
| 2014 | 60 | 297,926 | 15.0 |
| 2015 | 60 | -95,790 | 19.2 |
| 2016 | 60 | 112,210 | 22.4 |
| 2017 | 60 | 77,641 | 8.6 |
| 2018 | 60 | -72,438 | 23.3 |
| 2019 | 66 | -76,127 | 23.4 |
| 2020 | 69 | 341,995 | 34.9 |
| 2021 | 60 | 159,096 | 6.6 |
| 2022 | 60 | 71,084 | 8.9 |
| 2023 | 60 | 128,822 | 5.3 |
| 2024 | 60 | 237,800 | 6.1 |
| 2025 | 61 | 23,467 | 6.5 |
| 2026 | 70 | -42,607 | 6.4 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 7; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin102",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:102",
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
  "queue_max_runup": null,
  "sources": [],
  "delist_grace_days": 7
}
```
