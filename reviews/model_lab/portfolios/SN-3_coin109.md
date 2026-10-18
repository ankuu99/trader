# Portfolio sim `SN-3_coin109` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,137,774 · trades 988 · win rate 51.6% · PF 1.49 · money-weighted win % 59.8 · avg ₹1,152/trade · max DD ₹457,098 (44.8%) · ann. return 12.0% · Calmar 0.27 · mean utilisation 96.9% · avg held 59.3 bars

## Excluding 2020

net ₹953,163 · trades 920 · win rate 50.9% · PF 1.46 · money-weighted win % 59.3 · avg ₹1,036/trade · max DD ₹299,780 (44.8%) · ann. return 10.9% · Calmar 0.24 · mean utilisation 96.9% · avg held 59.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | -2,021 |
| END | 14 | 5,864 |
| TIME | 973 | 1,133,931 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 56 | -233,937 | 44.8 |
| 2012 | 64 | 183,758 | 25.9 |
| 2013 | 60 | -115,335 | 41.3 |
| 2014 | 60 | 381,307 | 15.0 |
| 2015 | 60 | -38,277 | 16.4 |
| 2016 | 60 | 129,066 | 19.3 |
| 2017 | 61 | 177,433 | 5.8 |
| 2018 | 61 | -108,705 | 19.9 |
| 2019 | 65 | -51,591 | 18.6 |
| 2020 | 68 | 184,611 | 27.8 |
| 2021 | 60 | 264,867 | 6.0 |
| 2022 | 61 | -13,779 | 8.1 |
| 2023 | 60 | 112,339 | 4.5 |
| 2024 | 60 | 158,579 | 5.8 |
| 2025 | 60 | 63,028 | 5.5 |
| 2026 | 72 | 44,411 | 4.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 2; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin109",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:109",
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
