"""
Central map: FVM factor concepts -> Trendlyne fincsv field names.

All Trendlyne field-name coupling lives HERE (the catalog is docs/FVM_Trendlyne_Fields.md).
Each entry is (statement, field) for FVMStore.read_fundamental_asof(symbol, statement,
basis, field, asof). Trendlyne pre-computes many factors (OPM%, Revenue-growth-YoY%,
EV/EBITDA, D/E, interest-coverage, ROCE) — we use those directly where available.
"""

# --- Pillar 1: Earnings (quarterly) ---
NET_PROFIT_Q       = ("quarter", "Net Profit Qtr")
TOTAL_REVENUE_Q    = ("quarter", "Total Revenue Qtr")
OPM_Q              = ("quarter", "Operating Profit Margin Qtr %")    # pre-computed %
REVENUE_GROWTH_Q   = ("quarter", "Revenue Growth Qtr YoY %")         # pre-computed YoY %
EBITDA_Q           = ("quarter", "EBITDA Qtr")

# --- Pillar 2: Valuation (annual snapshots; live PEG/P-E use Kite price + TTM EPS) ---
EV_EBITDA_A        = ("annual", "EV Per EBITDA Annual")              # pre-computed (no cash-gap)
EPS_A              = ("annual", "EPS Annual")
BASIC_EPS_Q        = ("quarter", "Basic EPS Qtr")                    # for TTM EPS (P/E, PEG)
EARNINGS_YIELD_A   = ("annual", "Earnings Yield Annual")            # = 1 / P/E (annual snapshot)
PRICE_TO_BOOK_A    = ("annual", "Price to Book Value Adjusted")

# --- Pillar 3: Balance sheet (annual) ---
CFO_A              = ("annual", "Cash from Operating Activity Annual")
NET_PROFIT_A       = ("annual", "Net Profit Annual")
DE_A               = ("annual", "Total Debt to Total Equity Annual")  # pre-computed
INT_COVERAGE_A     = ("annual", "Interest Coverage Ratio Annual")     # pre-computed
ROCE_A             = ("annual", "ROCE Annual %")                      # pre-computed
LT_DEBT_A          = ("annual", "Long Term Debt Annual")
ST_DEBT_A          = ("annual", "Short Term Debt Annual")

# --- Pillar 1 manufactured-earnings / revenue (annual, for the veto) ---
REVENUE_GROWTH_A   = ("annual", "Revenue Growth Annual YoY %")
NET_PROFIT_MARGIN_A = ("annual", "Net Profit Margin Annual %")
TOTAL_REVENUE_A    = ("annual", "Total Revenue Annual")  # TTM-revenue floor for annual-fallback yoy

# --- Long-term conviction study (annual; used by conviction.py, not the FVM strategy) ---
ROE_A              = ("annual", "ROE Annual %")                   # pre-computed return on equity
NET_PROFIT_3Y_A    = ("annual", "Net Profit 3Yr Growth %")       # 3yr profit CAGR
NET_PROFIT_5Y_A    = ("annual", "Net Profit 5Yr Growth %")       # 5yr profit CAGR
REVENUE_3Y_A       = ("annual", "Revenue Annual 3Yr Growth %")   # 3yr revenue CAGR
REVENUE_5Y_A       = ("annual", "Revenue Annual 5Yr Growth %")   # 5yr revenue CAGR
DIV_PER_SHARE_A    = ("annual", "Dividend Per Share Annual")
DIV_PAYOUT_A       = ("annual", "Dividend Payout to NP Annual")  # payout % of net profit
BOOK_VALUE_A       = ("annual", "Book Value Inc Reval Reserve Annual")
CFI_A              = ("annual", "Cash from Investing Activity Annual")  # for FCF ≈ CFO + capex

# --- Pillar 4: Ownership lives in the `shareholding` table (Screener), not fundamentals.
# Field keys used with FVMStore.read_shareholding_asof:
SH_PROMOTER = "promoter"
SH_FII      = "fii"
SH_DII      = "dii"
SH_PLEDGE   = "pledge"
SH_HOLDERS  = "holders"
