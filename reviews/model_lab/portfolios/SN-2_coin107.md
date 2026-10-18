# Portfolio sim `SN-2_coin107` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹524,385 · trades 1137 · win rate 52.9% · PF 1.19 · money-weighted win % 54.3 · avg ₹461/trade · max DD ₹399,783 (50.4%) · ann. return 5.5% · Calmar 0.11 · mean utilisation 96.7% · avg held 51.5 bars

## Excluding 2020

net ₹441,749 · trades 1055 · win rate 52.3% · PF 1.18 · money-weighted win % 54.0 · avg ₹419/trade · max DD ₹243,873 (40.6%) · ann. return 5.1% · Calmar 0.12 · mean utilisation 96.7% · avg held 52.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | 1,276 |
| END | 15 | -43,488 |
| TARGET | 314 | 2,476,553 |
| TIME | 807 | -1,909,957 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 59 | -166,020 | 37.0 |
| 2012 | 78 | 142,534 | 26.4 |
| 2013 | 71 | -90,151 | 39.9 |
| 2014 | 78 | 159,831 | 11.0 |
| 2015 | 70 | -31,571 | 15.3 |
| 2016 | 70 | 20,668 | 23.4 |
| 2017 | 69 | 115,376 | 6.8 |
| 2018 | 72 | -58,152 | 20.5 |
| 2019 | 66 | -35,707 | 20.8 |
| 2020 | 82 | 82,636 | 42.8 |
| 2021 | 74 | 190,063 | 6.7 |
| 2022 | 70 | -24,379 | 16.3 |
| 2023 | 72 | 131,754 | 7.3 |
| 2024 | 69 | 79,127 | 9.6 |
| 2025 | 71 | 58,157 | 9.8 |
| 2026 | 66 | -49,780 | 7.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 8; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin107",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:107",
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
