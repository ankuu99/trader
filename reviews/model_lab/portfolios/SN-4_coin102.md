# Portfolio sim `SN-4_coin102` (run `A07n_dayn_hgbq_mfe20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹492,047 · trades 2934 · win rate 50.2% · PF 1.11 · money-weighted win % 52.6 · avg ₹168/trade · max DD ₹545,000 (64.2%) · ann. return 5.2% · Calmar 0.08 · mean utilisation 93.5% · avg held 20.0 bars

## Excluding 2020

net ₹343,130 · trades 2745 · win rate 49.7% · PF 1.08 · money-weighted win % 52.0 · avg ₹125/trade · max DD ₹330,895 (47.8%) · ann. return 3.9% · Calmar 0.08 · mean utilisation 93.5% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | 966 |
| END | 14 | -12,859 |
| TIME | 2919 | 503,940 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 174 | -171,458 | 34.6 |
| 2012 | 186 | 131,006 | 31.8 |
| 2013 | 189 | -90,631 | 44.2 |
| 2014 | 183 | 243,015 | 12.6 |
| 2015 | 183 | -45,518 | 20.6 |
| 2016 | 187 | -9,109 | 20.7 |
| 2017 | 188 | 151,303 | 6.7 |
| 2018 | 181 | -173,829 | 34.3 |
| 2019 | 185 | -36,109 | 24.9 |
| 2020 | 189 | 148,916 | 52.9 |
| 2021 | 185 | 147,261 | 8.2 |
| 2022 | 186 | -1,955 | 18.1 |
| 2023 | 184 | 141,120 | 6.9 |
| 2024 | 185 | 66,444 | 8.8 |
| 2025 | 190 | 23,323 | 8.3 |
| 2026 | 159 | -31,732 | 7.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 14; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-4_coin102",
  "run_id": "A07n_dayn_hgbq_mfe20",
  "hold_bars": 20,
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
