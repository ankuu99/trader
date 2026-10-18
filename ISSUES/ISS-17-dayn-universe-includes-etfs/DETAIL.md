# ISS-17: `dayn` liquidity universe includes ETFs / fund units

## Report (main session, 2026-10-19)

Bhavcopy lists ETFs and other exchange-traded fund units under series EQ, and the L0c build put every security into
the `day_nse` liquidity panel. The Kite-based `day` universe excludes them (`universe._is_etf` on the instrument
snapshot). PIT top-200 on `dayn` therefore contained BANKBEES, GOLDBEES, LIQUIDBEES, LIQUIDCASE, NIFTYBEES and
SILVERBEES in some years, and the SN sims traded them: SN-1 49 trades (−₹10.3k), SN-2 41 (−₹0.9k), SN-3 23 (+₹1.1k).
That is small in ₹ but wrong. Of the 4,045 securities, 376 have an ISIN starting with `INF` (mutual-fund/ETF units).

## Proposed fix
In `build`, flag `is_fund` on `securities.parquet` (any ISIN starting with "INF", or `universe._is_etf("", last_symbol)`)
and build the `day_nse` liquidity panel from the non-fund securities only. Then re-run ML-A01n / ML-A11n and SN-1..3.
