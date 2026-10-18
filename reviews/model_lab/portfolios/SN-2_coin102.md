# Portfolio sim `SN-2_coin102` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹830,392 · trades 1153 · win rate 54.4% · PF 1.32 · money-weighted win % 56.9 · avg ₹720/trade · max DD ₹484,805 (43.4%) · ann. return 8.8% · Calmar 0.20 · mean utilisation 96.4% · avg held 50.8 bars

## Excluding 2020

net ₹699,705 · trades 1072 · win rate 53.7% · PF 1.29 · money-weighted win % 56.4 · avg ₹653/trade · max DD ₹287,761 (39.4%) · ann. return 8.0% · Calmar 0.20 · mean utilisation 96.4% · avg held 51.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 3 | -13,139 |
| END | 15 | -26,338 |
| TARGET | 342 | 2,683,587 |
| TIME | 793 | -1,813,717 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 60 | -185,117 | 39.4 |
| 2012 | 77 | 105,435 | 26.3 |
| 2013 | 78 | 25,327 | 24.1 |
| 2014 | 82 | 322,473 | 8.2 |
| 2015 | 69 | -21,783 | 13.2 |
| 2016 | 73 | 96,353 | 13.6 |
| 2017 | 71 | 157,897 | 4.3 |
| 2018 | 70 | -159,798 | 19.9 |
| 2019 | 69 | -73,101 | 15.8 |
| 2020 | 81 | 130,687 | 29.8 |
| 2021 | 73 | 175,188 | 4.9 |
| 2022 | 70 | 38,647 | 10.9 |
| 2023 | 71 | 129,031 | 9.1 |
| 2024 | 70 | 107,291 | 5.9 |
| 2025 | 71 | 49,032 | 6.9 |
| 2026 | 68 | -67,171 | 7.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin102",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:102",
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
