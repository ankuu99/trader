# Portfolio sim `SC3-M500-x0_prod` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹394,882 · trades 1589 · win rate 51.0% · PF 1.17 · money-weighted win % 54.0 · avg ₹249/trade · max DD ₹421,988 (62.3%) · ann. return 7.1% · Calmar 0.11 · mean utilisation 92.1% · avg held 498.4 bars

## Excluding 2020

net ₹374,085 · trades 1433 · win rate 51.1% · PF 1.20 · money-weighted win % 54.5 · avg ₹261/trade · max DD ₹247,458 (36.5%) · ann. return 7.7% · Calmar 0.21 · mean utilisation 92.1% · avg held 498.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -16,841 |
| TIME | 1574 | 411,723 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 31 | 39,639 | 5.9 |
| 2018 | 180 | -151,660 | 32.0 |
| 2019 | 177 | 12,243 | 19.7 |
| 2020 | 156 | 20,798 | 51.3 |
| 2021 | 178 | 187,494 | 10.5 |
| 2022 | 179 | 59,192 | 17.0 |
| 2023 | 178 | 139,684 | 9.3 |
| 2024 | 175 | 128,346 | 8.1 |
| 2025 | 182 | 17,394 | 6.3 |
| 2026 | 153 | -58,248 | 7.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x0_prod",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
