# Portfolio sim `SN-1_coin11` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹367,919 · trades 2932 · win rate 49.5% · PF 1.08 · money-weighted win % 51.9 · avg ₹125/trade · max DD ₹573,793 (92.5%) · ann. return 3.9% · Calmar 0.04 · mean utilisation 93.6% · avg held 20.0 bars

## Excluding 2020

net ₹298,121 · trades 2742 · win rate 49.3% · PF 1.07 · money-weighted win % 51.7 · avg ₹109/trade · max DD ₹476,441 (79.3%) · ann. return 3.4% · Calmar 0.04 · mean utilisation 93.6% · avg held 20.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 13 | -16,878 |
| TIME | 2919 | 384,797 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 175 | -266,585 | 53.5 |
| 2012 | 185 | 101,381 | 39.8 |
| 2013 | 189 | -115,818 | 72.6 |
| 2014 | 185 | 236,629 | 17.6 |
| 2015 | 181 | -121,865 | 30.8 |
| 2016 | 187 | -23,564 | 27.2 |
| 2017 | 187 | 184,941 | 7.9 |
| 2018 | 182 | -151,181 | 41.8 |
| 2019 | 184 | -78,805 | 37.1 |
| 2020 | 190 | 69,798 | 88.3 |
| 2021 | 184 | 195,086 | 11.7 |
| 2022 | 188 | -60,062 | 30.5 |
| 2023 | 183 | 243,093 | 7.1 |
| 2024 | 183 | 89,591 | 9.9 |
| 2025 | 191 | 86,814 | 8.1 |
| 2026 | 158 | -21,532 | 9.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 13; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-1_coin11",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 20,
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
