# Portfolio sim `SN-1_model` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹310,301 · trades 2830 · win rate 50.2% · PF 1.07 · money-weighted win % 51.6 · avg ₹110/trade · max DD ₹421,647 (55.1%) · ann. return 3.3% · Calmar 0.06 · mean utilisation 90.1% · avg held 19.9 bars

## Excluding 2020

net ₹203,156 · trades 2653 · win rate 49.8% · PF 1.05 · money-weighted win % 51.2 · avg ₹77/trade · max DD ₹384,346 (55.1%) · ann. return 2.3% · Calmar 0.04 · mean utilisation 90.1% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 2 | 10,920 |
| END | 15 | -8,599 |
| TIME | 2813 | 307,981 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 167 | -126,094 | 32.1 |
| 2012 | 177 | 178,416 | 19.7 |
| 2013 | 178 | -174,548 | 55.0 |
| 2014 | 175 | 162,724 | 12.1 |
| 2015 | 182 | 15,115 | 14.1 |
| 2016 | 171 | 20,666 | 17.7 |
| 2017 | 183 | 88,604 | 8.4 |
| 2018 | 182 | -137,922 | 31.9 |
| 2019 | 179 | -44,924 | 36.1 |
| 2020 | 177 | 107,145 | 41.5 |
| 2021 | 179 | 105,037 | 8.7 |
| 2022 | 180 | -53,488 | 23.8 |
| 2023 | 179 | 154,241 | 9.1 |
| 2024 | 180 | 16,483 | 8.9 |
| 2025 | 182 | 8,757 | 8.8 |
| 2026 | 159 | -9,910 | 11.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 31; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-1_model",
  "run_id": "A01n_dayn_logit_t1z5",
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
