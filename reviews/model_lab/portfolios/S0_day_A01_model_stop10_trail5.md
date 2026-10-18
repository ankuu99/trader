# Portfolio sim `S0_day_A01_model_stop10_trail5` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹380,785 · trades 2730 · win rate 50.2% · PF 1.10 · money-weighted win % 52.3 · avg ₹139/trade · max DD ₹481,283 (46.4%) · ann. return 4.0% · Calmar 0.09 · mean utilisation 59.4% · avg held 13.6 bars

## Excluding 2020

net ₹483,373 · trades 2552 · win rate 50.7% · PF 1.14 · money-weighted win % 53.2 · avg ₹189/trade · max DD ₹323,061 (37.7%) · ann. return 5.5% · Calmar 0.15 · mean utilisation 59.4% · avg held 13.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 10,045 |
| STOP | 775 | -3,219,645 |
| TIME | 1150 | 1,956,535 |
| TRAIL | 790 | 1,633,851 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 131 | -50,988 | 18.9 |
| 2012 | 138 | 106,779 | 18.7 |
| 2013 | 217 | -105,817 | 36.2 |
| 2014 | 169 | 194,653 | 4.5 |
| 2015 | 183 | -31,307 | 14.9 |
| 2016 | 198 | 33,359 | 16.3 |
| 2017 | 148 | 140,595 | 15.2 |
| 2018 | 211 | -57,141 | 13.8 |
| 2019 | 193 | -62,115 | 15.8 |
| 2020 | 178 | -102,588 | 30.9 |
| 2021 | 163 | 153,327 | 6.9 |
| 2022 | 153 | 41,697 | 7.8 |
| 2023 | 167 | 138,489 | 7.9 |
| 2024 | 165 | 37,595 | 8.6 |
| 2025 | 154 | -6,588 | 7.3 |
| 2026 | 162 | -49,165 | 11.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 18.

## Spec

```json
{
  "sim_id": "S0_day_A01_model_stop10_trail5",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "run",
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
