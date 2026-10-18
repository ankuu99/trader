# Portfolio sim `SN-2_coin103` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹773,247 · trades 1163 · win rate 55.4% · PF 1.28 · money-weighted win % 56.1 · avg ₹665/trade · max DD ₹392,572 (50.6%) · ann. return 8.2% · Calmar 0.16 · mean utilisation 96.8% · avg held 50.4 bars

## Excluding 2020

net ₹593,540 · trades 1075 · win rate 54.0% · PF 1.23 · money-weighted win % 55.2 · avg ₹552/trade · max DD ₹312,290 (50.6%) · ann. return 6.8% · Calmar 0.13 · mean utilisation 96.8% · avg held 50.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 4 | -6,474 |
| END | 15 | -21,018 |
| TARGET | 354 | 2,788,295 |
| TIME | 790 | -1,987,555 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 58 | -246,163 | 50.6 |
| 2012 | 78 | 128,272 | 22.7 |
| 2013 | 73 | -27,875 | 37.8 |
| 2014 | 79 | 234,665 | 12.4 |
| 2015 | 71 | 20,104 | 17.5 |
| 2016 | 73 | 65,694 | 21.8 |
| 2017 | 70 | 89,917 | 4.9 |
| 2018 | 72 | -75,372 | 22.8 |
| 2019 | 68 | -84,529 | 24.8 |
| 2020 | 88 | 179,707 | 32.7 |
| 2021 | 79 | 247,845 | 5.4 |
| 2022 | 66 | 15,916 | 12.8 |
| 2023 | 74 | 117,645 | 7.7 |
| 2024 | 77 | 140,851 | 6.1 |
| 2025 | 67 | -25,072 | 6.4 |
| 2026 | 70 | -8,358 | 6.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 6; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin103",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:103",
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
