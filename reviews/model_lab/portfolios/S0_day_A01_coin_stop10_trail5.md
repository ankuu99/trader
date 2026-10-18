# Portfolio sim `S0_day_A01_coin_stop10_trail5` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹720,603 · trades 3521 · win rate 49.6% · PF 1.15 · money-weighted win % 53.5 · avg ₹205/trade · max DD ₹385,321 (61.9%) · ann. return 7.6% · Calmar 0.12 · mean utilisation 86.2% · avg held 15.2 bars

## Excluding 2020

net ₹545,096 · trades 3262 · win rate 49.2% · PF 1.12 · money-weighted win % 52.9 · avg ₹167/trade · max DD ₹385,321 (61.9%) · ann. return 6.3% · Calmar 0.10 · mean utilisation 86.2% · avg held 15.4 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 13 | 8,531 |
| STOP | 898 | -3,699,058 |
| TIME | 1680 | 2,590,854 |
| TRAIL | 930 | 1,820,276 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 181 | -220,289 | 40.5 |
| 2012 | 230 | 61,274 | 33.2 |
| 2013 | 246 | -12,428 | 49.2 |
| 2014 | 223 | 210,035 | 13.8 |
| 2015 | 230 | -19,547 | 18.2 |
| 2016 | 220 | -35,801 | 16.4 |
| 2017 | 206 | 194,615 | 7.4 |
| 2018 | 239 | -22,800 | 16.0 |
| 2019 | 230 | -81 | 14.7 |
| 2020 | 259 | 175,507 | 27.3 |
| 2021 | 218 | 231,502 | 5.2 |
| 2022 | 221 | 4,847 | 14.4 |
| 2023 | 199 | 203,958 | 5.8 |
| 2024 | 221 | 107,216 | 5.6 |
| 2025 | 213 | -61,985 | 6.5 |
| 2026 | 185 | -95,421 | 10.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 17.

## Spec

```json
{
  "sim_id": "S0_day_A01_coin_stop10_trail5",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": 0.1,
  "target_pct": null,
  "trail_pct": 0.05,
  "trail_activate_pct": 0.05,
  "reentry_gap_bars": 0,
  "exclusions": []
}
```
