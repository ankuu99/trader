# Portfolio sim `SN-4_coin106` (run `A07n_dayn_hgbq_mfe20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹724,217 · trades 2933 · win rate 50.6% · PF 1.16 · money-weighted win % 53.8 · avg ₹247/trade · max DD ₹589,581 (60.2%) · ann. return 7.6% · Calmar 0.13 · mean utilisation 93.5% · avg held 19.9 bars

## Excluding 2020

net ₹547,207 · trades 2741 · win rate 50.2% · PF 1.13 · money-weighted win % 53.1 · avg ₹200/trade · max DD ₹407,735 (49.8%) · ann. return 6.3% · Calmar 0.13 · mean utilisation 93.5% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | -2,496 |
| END | 15 | -3,399 |
| TIME | 2917 | 730,113 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 175 | -258,120 | 49.8 |
| 2012 | 185 | 227,909 | 30.6 |
| 2013 | 189 | -127,210 | 43.1 |
| 2014 | 184 | 258,827 | 11.2 |
| 2015 | 182 | 27,810 | 14.3 |
| 2016 | 184 | 43,872 | 13.1 |
| 2017 | 190 | 156,092 | 5.6 |
| 2018 | 181 | -123,002 | 24.0 |
| 2019 | 183 | -199,912 | 29.5 |
| 2020 | 192 | 177,011 | 39.2 |
| 2021 | 183 | 192,896 | 8.9 |
| 2022 | 186 | 35,923 | 10.4 |
| 2023 | 186 | 115,404 | 7.3 |
| 2024 | 185 | 142,521 | 6.3 |
| 2025 | 186 | 9,662 | 9.5 |
| 2026 | 162 | 44,535 | 5.4 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 10; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-4_coin106",
  "run_id": "A07n_dayn_hgbq_mfe20",
  "hold_bars": 20,
  "score_source": "coin:106",
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
