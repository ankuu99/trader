# Portfolio sim `SN-3_coin104` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹835,678 · trades 988 · win rate 50.4% · PF 1.33 · money-weighted win % 57.0 · avg ₹846/trade · max DD ₹506,396 (57.6%) · ann. return 8.8% · Calmar 0.15 · mean utilisation 97.0% · avg held 59.3 bars

## Excluding 2020

net ₹551,656 · trades 920 · win rate 49.6% · PF 1.25 · money-weighted win % 55.5 · avg ₹600/trade · max DD ₹287,342 (40.8%) · ann. return 6.3% · Calmar 0.15 · mean utilisation 97.0% · avg held 59.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | 3,357 |
| END | 13 | 794 |
| TIME | 974 | 831,527 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 55 | -189,799 | 37.0 |
| 2012 | 65 | 175,132 | 27.7 |
| 2013 | 60 | -54,700 | 40.8 |
| 2014 | 61 | 280,450 | 14.3 |
| 2015 | 60 | -96,835 | 20.7 |
| 2016 | 60 | 63,825 | 18.5 |
| 2017 | 60 | 58,209 | 6.0 |
| 2018 | 61 | -170,699 | 28.4 |
| 2019 | 65 | -42,354 | 19.2 |
| 2020 | 68 | 284,022 | 44.1 |
| 2021 | 60 | 172,484 | 5.7 |
| 2022 | 61 | -5,499 | 14.3 |
| 2023 | 60 | 76,501 | 7.4 |
| 2024 | 60 | 243,724 | 4.7 |
| 2025 | 60 | 5,275 | 9.4 |
| 2026 | 72 | 35,944 | 6.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 2; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin104",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:104",
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
