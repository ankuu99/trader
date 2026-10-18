# Portfolio sim `SN-1_coin109` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹617,528 · trades 2935 · win rate 49.9% · PF 1.14 · money-weighted win % 53.3 · avg ₹210/trade · max DD ₹417,494 (54.0%) · ann. return 6.5% · Calmar 0.12 · mean utilisation 93.6% · avg held 19.9 bars

## Excluding 2020

net ₹404,697 · trades 2745 · win rate 49.3% · PF 1.10 · money-weighted win % 52.4 · avg ₹147/trade · max DD ₹324,181 (54.0%) · ann. return 4.6% · Calmar 0.09 · mean utilisation 93.6% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 2 | -534 |
| END | 14 | 1,801 |
| TIME | 2919 | 616,261 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 175 | -255,916 | 48.4 |
| 2012 | 185 | 152,810 | 25.6 |
| 2013 | 189 | -98,593 | 47.8 |
| 2014 | 186 | 271,400 | 15.1 |
| 2015 | 180 | -85,773 | 22.9 |
| 2016 | 188 | 47,498 | 17.3 |
| 2017 | 187 | 163,250 | 6.4 |
| 2018 | 180 | -125,037 | 25.4 |
| 2019 | 185 | -29,705 | 17.5 |
| 2020 | 190 | 212,831 | 43.4 |
| 2021 | 184 | 166,107 | 9.6 |
| 2022 | 188 | -21,873 | 16.0 |
| 2023 | 183 | 146,953 | 7.2 |
| 2024 | 185 | 6,190 | 9.5 |
| 2025 | 188 | 73,513 | 7.0 |
| 2026 | 162 | -6,126 | 8.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 10; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-1_coin109",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 20,
  "score_source": "coin:109",
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
