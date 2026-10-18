# Portfolio sim `SN-3_coin11` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹507,113 · trades 986 · win rate 49.7% · PF 1.18 · money-weighted win % 54.2 · avg ₹514/trade · max DD ₹527,557 (87.8%) · ann. return 5.4% · Calmar 0.06 · mean utilisation 97.0% · avg held 59.4 bars

## Excluding 2020

net ₹229,260 · trades 916 · win rate 49.0% · PF 1.09 · money-weighted win % 52.2 · avg ₹250/trade · max DD ₹527,557 (87.8%) · ann. return 2.6% · Calmar 0.03 · mean utilisation 97.0% · avg held 59.3 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 2 | 5,336 |
| END | 14 | -724 |
| TIME | 970 | 502,502 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 56 | -313,632 | 57.5 |
| 2012 | 64 | 137,093 | 30.1 |
| 2013 | 60 | -202,011 | 83.3 |
| 2014 | 60 | 307,919 | 22.6 |
| 2015 | 60 | -70,532 | 21.8 |
| 2016 | 60 | 5,722 | 31.8 |
| 2017 | 60 | 109,658 | 13.7 |
| 2018 | 62 | -64,190 | 28.6 |
| 2019 | 63 | -54,155 | 32.5 |
| 2020 | 70 | 277,853 | 56.2 |
| 2021 | 60 | 215,574 | 8.1 |
| 2022 | 60 | -34,697 | 17.3 |
| 2023 | 60 | 85,520 | 8.5 |
| 2024 | 60 | 160,556 | 8.1 |
| 2025 | 61 | 29,218 | 9.7 |
| 2026 | 70 | -82,784 | 11.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 7; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin11",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:11",
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
