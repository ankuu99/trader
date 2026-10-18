# Portfolio sim `SN-2_coin108` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹617,683 · trades 1146 · win rate 53.5% · PF 1.23 · money-weighted win % 55.1 · avg ₹539/trade · max DD ₹602,452 (77.7%) · ann. return 6.5% · Calmar 0.08 · mean utilisation 96.7% · avg held 51.1 bars

## Excluding 2020

net ₹425,380 · trades 1052 · win rate 52.0% · PF 1.17 · money-weighted win % 53.9 · avg ₹404/trade · max DD ₹436,302 (56.2%) · ann. return 4.9% · Calmar 0.09 · mean utilisation 96.7% · avg held 52.1 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 2 | -776 |
| END | 15 | -30,200 |
| TARGET | 325 | 2,566,658 |
| TIME | 804 | -1,918,000 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 60 | -199,088 | 45.2 |
| 2012 | 74 | 98,662 | 23.6 |
| 2013 | 67 | -103,730 | 43.6 |
| 2014 | 80 | 213,601 | 16.4 |
| 2015 | 70 | -21,788 | 26.8 |
| 2016 | 71 | 27,980 | 23.4 |
| 2017 | 73 | 106,731 | 11.8 |
| 2018 | 69 | -135,232 | 31.5 |
| 2019 | 64 | -190,764 | 44.3 |
| 2020 | 94 | 192,303 | 60.0 |
| 2021 | 77 | 261,043 | 8.8 |
| 2022 | 68 | 7,763 | 14.8 |
| 2023 | 71 | 144,954 | 7.8 |
| 2024 | 72 | 171,704 | 6.0 |
| 2025 | 69 | 20,609 | 7.8 |
| 2026 | 67 | 22,937 | 7.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin108",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:108",
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
