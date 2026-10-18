# Portfolio sim `SN-2_coin101` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹889,114 · trades 1157 · win rate 54.4% · PF 1.34 · money-weighted win % 57.2 · avg ₹768/trade · max DD ₹324,507 (51.5%) · ann. return 9.4% · Calmar 0.18 · mean utilisation 96.6% · avg held 50.6 bars

## Excluding 2020

net ₹832,654 · trades 1078 · win rate 53.6% · PF 1.35 · money-weighted win % 57.5 · avg ₹772/trade · max DD ₹308,973 (51.5%) · ann. return 9.5% · Calmar 0.19 · mean utilisation 96.6% · avg held 50.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -27,231 |
| TARGET | 341 | 2,701,832 |
| TIME | 801 | -1,785,487 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 62 | -197,871 | 40.9 |
| 2012 | 79 | 130,551 | 25.5 |
| 2013 | 72 | -67,518 | 48.0 |
| 2014 | 84 | 253,082 | 15.4 |
| 2015 | 65 | -40,136 | 14.4 |
| 2016 | 74 | 70,801 | 19.9 |
| 2017 | 74 | 204,171 | 6.2 |
| 2018 | 71 | -4,987 | 11.7 |
| 2019 | 72 | -10,545 | 13.3 |
| 2020 | 79 | 56,460 | 27.2 |
| 2021 | 74 | 233,690 | 4.8 |
| 2022 | 71 | -55,577 | 9.8 |
| 2023 | 73 | 183,010 | 5.5 |
| 2024 | 70 | 181,739 | 5.7 |
| 2025 | 69 | -12,939 | 4.2 |
| 2026 | 68 | -34,817 | 5.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 1; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin101",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:101",
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
