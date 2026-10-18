# Portfolio sim `S0_15m_A05_coin_time125` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹69,317 · trades 6538 · win rate 49.2% · PF 1.01 · money-weighted win % 50.4 · avg ₹11/trade · max DD ₹518,415 (72.4%) · ann. return 1.2% · Calmar 0.02 · mean utilisation 94.5% · avg held 124.9 bars

## Excluding 2020

net ₹96,599 · trades 5804 · win rate 48.9% · PF 1.02 · money-weighted win % 50.6 · avg ₹17/trade · max DD ₹316,820 (44.2%) · ann. return 2.0% · Calmar 0.04 · mean utilisation 94.5% · avg held 124.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -1,918 |
| TIME | 6523 | 71,235 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 170 | 83,434 | 5.5 |
| 2018 | 715 | -106,591 | 26.6 |
| 2019 | 718 | -72,409 | 28.0 |
| 2020 | 734 | -27,282 | 62.8 |
| 2021 | 722 | 16,071 | 16.6 |
| 2022 | 723 | 40,688 | 28.1 |
| 2023 | 718 | 111,080 | 14.3 |
| 2024 | 723 | 119,922 | 7.8 |
| 2025 | 729 | -33,286 | 16.3 |
| 2026 | 586 | -62,310 | 14.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 9.

## Spec

```json
{
  "sim_id": "S0_15m_A05_coin_time125",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 125,
  "score_source": "ref:coin",
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
  "exclusions": []
}
```
