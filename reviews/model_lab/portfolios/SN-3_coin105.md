# Portfolio sim `SN-3_coin105` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹609,652 · trades 988 · win rate 50.5% · PF 1.23 · money-weighted win % 55.3 · avg ₹617/trade · max DD ₹436,374 (72.7%) · ann. return 6.4% · Calmar 0.09 · mean utilisation 97.1% · avg held 59.3 bars

## Excluding 2020

net ₹435,895 · trades 919 · win rate 49.0% · PF 1.18 · money-weighted win % 54.2 · avg ₹474/trade · max DD ₹436,374 (72.7%) · ann. return 5.0% · Calmar 0.07 · mean utilisation 97.1% · avg held 59.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -7,774 |
| TIME | 974 | 617,426 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 57 | -304,515 | 56.4 |
| 2012 | 63 | 122,842 | 31.6 |
| 2013 | 60 | -91,865 | 64.4 |
| 2014 | 60 | 333,963 | 28.6 |
| 2015 | 60 | -41,541 | 16.3 |
| 2016 | 60 | 53,915 | 23.2 |
| 2017 | 60 | 109,840 | 7.9 |
| 2018 | 61 | -34,873 | 14.7 |
| 2019 | 65 | -58,596 | 19.2 |
| 2020 | 69 | 173,757 | 33.4 |
| 2021 | 60 | 174,390 | 6.4 |
| 2022 | 60 | -46,822 | 14.7 |
| 2023 | 60 | 150,331 | 7.7 |
| 2024 | 60 | 163,355 | 7.1 |
| 2025 | 60 | -47,583 | 8.5 |
| 2026 | 73 | -46,945 | 7.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 6; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin105",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:105",
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
