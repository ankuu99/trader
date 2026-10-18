# ISS-17: `dayn` liquidity universe includes ETFs / fund units

- **Area:** Model Lab data (TD-022 L0c, `research/model_lab/nse_bhav.py::build` → `liquidity_day_nse.parquet`)
- **Status:** FIXED 2026-10-19 (ef6d50e) — fund securities (ISIN INF… or ETF name rule) flagged and kept out of the `day_nse` liquidity panel; panel rebuilt 2026-10-19, ever-members 505, no ETFs
- **Source:** Main session, 2026-10-19 (SN-1..3 trade audit)
- **Fix commits:** ef6d50e
