# Portfolio sim `SN-2_coin105` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹810,652 · trades 1164 · win rate 55.1% · PF 1.29 · money-weighted win % 56.4 · avg ₹696/trade · max DD ₹467,253 (48.7%) · ann. return 8.6% · Calmar 0.18 · mean utilisation 96.6% · avg held 50.3 bars

## Excluding 2020

net ₹727,255 · trades 1078 · win rate 54.3% · PF 1.29 · money-weighted win % 56.4 · avg ₹675/trade · max DD ₹292,138 (48.7%) · ann. return 8.3% · Calmar 0.17 · mean utilisation 96.6% · avg held 50.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | 5,670 |
| END | 15 | -35,571 |
| TARGET | 357 | 2,819,058 |
| TIME | 791 | -1,978,505 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 58 | -233,329 | 48.0 |
| 2012 | 82 | 96,812 | 28.6 |
| 2013 | 73 | -35,357 | 35.9 |
| 2014 | 84 | 283,963 | 15.3 |
| 2015 | 68 | 7,552 | 17.0 |
| 2016 | 70 | 55,333 | 17.8 |
| 2017 | 78 | 255,829 | 5.5 |
| 2018 | 70 | -116,055 | 18.2 |
| 2019 | 68 | 2,067 | 14.9 |
| 2020 | 86 | 83,396 | 34.9 |
| 2021 | 76 | 262,071 | 4.4 |
| 2022 | 70 | 1,750 | 10.3 |
| 2023 | 77 | 144,010 | 5.0 |
| 2024 | 69 | 69,879 | 5.8 |
| 2025 | 67 | 21,838 | 6.5 |
| 2026 | 68 | -89,107 | 7.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 1; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin105",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:105",
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
