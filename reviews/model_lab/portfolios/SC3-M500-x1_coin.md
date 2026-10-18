# Portfolio sim `SC3-M500-x1_coin` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹383,686 · trades 1685 · win rate 51.0% · PF 1.16 · money-weighted win % 53.7 · avg ₹228/trade · max DD ₹523,462 (73.0%) · ann. return 6.9% · Calmar 0.09 · mean utilisation 95.5% · avg held 487.0 bars

## Excluding 2020

net ₹279,405 · trades 1477 · win rate 50.7% · PF 1.14 · money-weighted win % 53.4 · avg ₹189/trade · max DD ₹253,531 (35.4%) · ann. return 5.7% · Calmar 0.16 · mean utilisation 95.5% · avg held 493.5 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 1,704 |
| STOP | 84 | -685,799 |
| TIME | 1586 | 1,067,782 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 45 | 103,011 | 5.1 |
| 2018 | 178 | -175,546 | 34.1 |
| 2019 | 182 | -8,869 | 24.7 |
| 2020 | 208 | 104,281 | 65.3 |
| 2021 | 180 | 171,909 | 10.0 |
| 2022 | 186 | 27,153 | 18.4 |
| 2023 | 182 | 121,862 | 7.9 |
| 2024 | 185 | 57,851 | 5.8 |
| 2025 | 183 | 47,163 | 10.7 |
| 2026 | 156 | -65,128 | 10.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x1_coin",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": 0.2,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
