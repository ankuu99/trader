# Portfolio sim `SN-3_coin101` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹948,363 · trades 989 · win rate 52.0% · PF 1.40 · money-weighted win % 58.4 · avg ₹959/trade · max DD ₹392,772 (65.5%) · ann. return 10.0% · Calmar 0.15 · mean utilisation 97.0% · avg held 59.2 bars

## Excluding 2020

net ₹819,062 · trades 921 · win rate 50.9% · PF 1.39 · money-weighted win % 58.1 · avg ₹889/trade · max DD ₹392,772 (65.5%) · ann. return 9.4% · Calmar 0.14 · mean utilisation 97.0% · avg held 59.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | -2,021 |
| END | 14 | 1,679 |
| TIME | 974 | 948,705 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 58 | -250,805 | 45.0 |
| 2012 | 62 | 130,965 | 27.4 |
| 2013 | 60 | -83,509 | 60.5 |
| 2014 | 60 | 324,679 | 10.0 |
| 2015 | 60 | 14,310 | 14.9 |
| 2016 | 60 | 85,484 | 14.5 |
| 2017 | 61 | 134,945 | 6.1 |
| 2018 | 61 | -64,749 | 17.7 |
| 2019 | 65 | -33,519 | 18.3 |
| 2020 | 68 | 129,302 | 29.6 |
| 2021 | 60 | 271,708 | 3.6 |
| 2022 | 61 | 58,547 | 9.2 |
| 2023 | 60 | 123,506 | 6.8 |
| 2024 | 60 | 111,561 | 6.3 |
| 2025 | 60 | 10,553 | 7.4 |
| 2026 | 73 | -14,615 | 6.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin101",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:101",
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
