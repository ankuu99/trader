# Portfolio sim `SN-1_coin107` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹275,564 · trades 2934 · win rate 49.3% · PF 1.06 · money-weighted win % 51.5 · avg ₹94/trade · max DD ₹499,650 (63.6%) · ann. return 2.9% · Calmar 0.05 · mean utilisation 93.6% · avg held 20.0 bars

## Excluding 2020

net ₹133,449 · trades 2744 · win rate 49.0% · PF 1.03 · money-weighted win % 50.8 · avg ₹49/trade · max DD ₹382,387 (63.6%) · ann. return 1.5% · Calmar 0.02 · mean utilisation 93.6% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 2 | 752 |
| END | 14 | -9,880 |
| TIME | 2918 | 284,692 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 175 | -250,056 | 44.3 |
| 2012 | 186 | 138,591 | 29.2 |
| 2013 | 188 | -159,673 | 56.8 |
| 2014 | 183 | 269,708 | 18.1 |
| 2015 | 184 | 6,415 | 13.7 |
| 2016 | 187 | -9,664 | 26.0 |
| 2017 | 186 | 181,230 | 9.0 |
| 2018 | 183 | -70,698 | 22.1 |
| 2019 | 184 | -126,589 | 27.6 |
| 2020 | 190 | 142,115 | 47.5 |
| 2021 | 185 | 125,585 | 11.9 |
| 2022 | 187 | 2,771 | 15.3 |
| 2023 | 183 | 109,986 | 10.1 |
| 2024 | 186 | 92,235 | 8.1 |
| 2025 | 188 | -57,438 | 12.4 |
| 2026 | 159 | -118,953 | 13.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 15; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-1_coin107",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 20,
  "score_source": "coin:107",
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
