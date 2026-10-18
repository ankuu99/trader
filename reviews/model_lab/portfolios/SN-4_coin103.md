# Portfolio sim `SN-4_coin103` (run `A07n_dayn_hgbq_mfe20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹270,151 · trades 2934 · win rate 50.3% · PF 1.06 · money-weighted win % 51.4 · avg ₹92/trade · max DD ₹421,744 (69.3%) · ann. return 2.9% · Calmar 0.04 · mean utilisation 93.5% · avg held 19.9 bars

## Excluding 2020

net ₹137,195 · trades 2742 · win rate 49.8% · PF 1.03 · money-weighted win % 50.8 · avg ₹50/trade · max DD ₹415,536 (69.3%) · ann. return 1.6% · Calmar 0.02 · mean utilisation 93.5% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 3 | -1,633 |
| END | 15 | -8,670 |
| TIME | 2916 | 280,453 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 175 | -273,195 | 49.7 |
| 2012 | 185 | 155,169 | 20.3 |
| 2013 | 188 | -167,811 | 63.5 |
| 2014 | 184 | 235,759 | 20.1 |
| 2015 | 183 | -91,970 | 27.2 |
| 2016 | 186 | -376 | 30.6 |
| 2017 | 189 | 155,166 | 7.0 |
| 2018 | 181 | 13,169 | 20.1 |
| 2019 | 182 | -110,504 | 25.9 |
| 2020 | 192 | 132,956 | 53.5 |
| 2021 | 183 | 158,354 | 8.7 |
| 2022 | 189 | -6,533 | 17.3 |
| 2023 | 183 | 115,601 | 10.8 |
| 2024 | 185 | 36,733 | 10.7 |
| 2025 | 190 | -31,998 | 11.6 |
| 2026 | 159 | -50,370 | 10.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 19; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-4_coin103",
  "run_id": "A07n_dayn_hgbq_mfe20",
  "hold_bars": 20,
  "score_source": "coin:103",
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
