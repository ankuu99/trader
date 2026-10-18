# Portfolio sim `SN-4_coin110` (run `A07n_dayn_hgbq_mfe20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹259,604 · trades 2931 · win rate 50.1% · PF 1.06 · money-weighted win % 51.4 · avg ₹89/trade · max DD ₹697,792 (105.3%) · ann. return 2.7% · Calmar 0.03 · mean utilisation 93.6% · avg held 20.0 bars

## Excluding 2020

net ₹57,826 · trades 2740 · win rate 49.4% · PF 1.01 · money-weighted win % 50.3 · avg ₹21/trade · max DD ₹501,288 (75.7%) · ann. return 0.7% · Calmar 0.01 · mean utilisation 93.6% · avg held 20.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | -3,680 |
| END | 13 | -19,054 |
| TIME | 2917 | 282,338 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 176 | -328,306 | 59.6 |
| 2012 | 184 | 204,401 | 21.3 |
| 2013 | 189 | -122,323 | 57.9 |
| 2014 | 184 | 242,171 | 20.3 |
| 2015 | 182 | -42,954 | 25.2 |
| 2016 | 187 | -52,533 | 30.3 |
| 2017 | 188 | 82,080 | 10.7 |
| 2018 | 180 | -209,783 | 46.8 |
| 2019 | 184 | -124,624 | 59.3 |
| 2020 | 191 | 201,778 | 113.0 |
| 2021 | 182 | 221,147 | 12.2 |
| 2022 | 187 | -52,713 | 16.8 |
| 2023 | 186 | 154,090 | 12.1 |
| 2024 | 184 | 74,134 | 9.0 |
| 2025 | 189 | 45,972 | 10.7 |
| 2026 | 158 | -32,934 | 11.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 9; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-4_coin110",
  "run_id": "A07n_dayn_hgbq_mfe20",
  "hold_bars": 20,
  "score_source": "coin:110",
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
