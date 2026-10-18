# Portfolio sim `SN-2_coin109` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹877,568 · trades 1161 · win rate 54.2% · PF 1.32 · money-weighted win % 57.0 · avg ₹756/trade · max DD ₹437,028 (44.2%) · ann. return 9.3% · Calmar 0.21 · mean utilisation 96.4% · avg held 50.5 bars

## Excluding 2020

net ₹797,745 · trades 1080 · win rate 53.5% · PF 1.32 · money-weighted win % 57.0 · avg ₹739/trade · max DD ₹309,920 (44.2%) · ann. return 9.1% · Calmar 0.21 · mean utilisation 96.4% · avg held 50.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | 648 |
| END | 15 | -39,635 |
| TARGET | 368 | 2,897,227 |
| TIME | 777 | -1,980,672 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 59 | -163,220 | 36.4 |
| 2012 | 82 | 219,959 | 13.1 |
| 2013 | 72 | -98,096 | 44.2 |
| 2014 | 85 | 292,373 | 6.4 |
| 2015 | 67 | -471 | 10.4 |
| 2016 | 73 | 59,202 | 15.0 |
| 2017 | 71 | 185,077 | 4.6 |
| 2018 | 71 | -163,066 | 23.0 |
| 2019 | 71 | -11,331 | 10.0 |
| 2020 | 81 | 79,824 | 28.2 |
| 2021 | 81 | 322,365 | 4.7 |
| 2022 | 70 | -58,362 | 13.3 |
| 2023 | 75 | 158,839 | 3.3 |
| 2024 | 65 | 115,840 | 5.1 |
| 2025 | 68 | -8,145 | 8.5 |
| 2026 | 70 | -53,221 | 5.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin109",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:109",
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
