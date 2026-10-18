# Portfolio sim `SN-4_model` (run `A07n_dayn_hgbq_mfe20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹161,300 · trades 955 · win rate 44.6% · PF 1.06 · money-weighted win % 51.4 · avg ₹169/trade · max DD ₹573,151 (89.0%) · ann. return 1.7% · Calmar 0.02 · mean utilisation 30.8% · avg held 20.0 bars

## Excluding 2020

net ₹-133,025 · trades 885 · win rate 43.3% · PF 0.95 · money-weighted win % 48.7 · avg ₹-150/trade · max DD ₹511,574 (79.5%) · ann. return -1.5% · Calmar -0.02 · mean utilisation 30.8% · avg held 20.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 3 | 3,541 |
| TIME | 952 | 157,759 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 76 | -158,605 | 32.2 |
| 2012 | 70 | 53,571 | 23.6 |
| 2013 | 56 | -168,696 | 42.3 |
| 2014 | 76 | 4,954 | 33.5 |
| 2015 | 56 | -42,127 | 34.6 |
| 2016 | 54 | -6,315 | 24.6 |
| 2017 | 57 | 104,541 | 19.0 |
| 2018 | 50 | -10,955 | 21.5 |
| 2019 | 56 | -186,020 | 57.4 |
| 2020 | 70 | 294,325 | 63.4 |
| 2021 | 61 | 40,169 | 9.6 |
| 2022 | 54 | -12,476 | 16.7 |
| 2023 | 48 | 92,903 | 12.2 |
| 2024 | 64 | 109,234 | 8.5 |
| 2025 | 62 | 9,788 | 12.3 |
| 2026 | 45 | 37,009 | 5.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-4_model",
  "run_id": "A07n_dayn_hgbq_mfe20",
  "hold_bars": 20,
  "score_source": "run",
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
