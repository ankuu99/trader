# Portfolio sim `SN-1_coin101` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹731,312 · trades 2935 · win rate 51.9% · PF 1.16 · money-weighted win % 53.8 · avg ₹249/trade · max DD ₹473,251 (65.2%) · ann. return 7.7% · Calmar 0.12 · mean utilisation 93.6% · avg held 19.9 bars

## Excluding 2020

net ₹538,407 · trades 2744 · win rate 51.3% · PF 1.13 · money-weighted win % 53.1 · avg ₹196/trade · max DD ₹391,438 (65.2%) · ann. return 6.2% · Calmar 0.09 · mean utilisation 93.6% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 3 | 3,602 |
| END | 14 | -14,862 |
| TIME | 2918 | 742,572 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 176 | -261,255 | 46.9 |
| 2012 | 184 | 129,091 | 31.8 |
| 2013 | 189 | -125,699 | 58.1 |
| 2014 | 184 | 201,559 | 21.1 |
| 2015 | 182 | -5,112 | 22.8 |
| 2016 | 187 | 51,454 | 26.4 |
| 2017 | 187 | 220,077 | 6.1 |
| 2018 | 182 | -45,946 | 23.9 |
| 2019 | 183 | -48,110 | 17.5 |
| 2020 | 191 | 192,905 | 42.9 |
| 2021 | 184 | 249,330 | 7.1 |
| 2022 | 187 | -75,428 | 15.4 |
| 2023 | 184 | 179,526 | 4.9 |
| 2024 | 186 | 117,185 | 6.6 |
| 2025 | 190 | 8,776 | 7.1 |
| 2026 | 159 | -57,042 | 7.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-1_coin101",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 20,
  "score_source": "coin:101",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": null,
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
