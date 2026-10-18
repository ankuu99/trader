# TD-022: Survivorship-free (delisting-inclusive) daily universe for the Model Lab

Discovered 2026-10-18 while checking Model Lab arm A07 (`reviews/model_lab/L2_day_round1_20261018.md`, addendum
"pick-composition check"). Kite's instrument list and historical API cover only currently listed stocks, so every lab
universe is survivor-biased: stocks that crashed and were delisted (e.g. DHFL, Reliance Capital) are missing while the
crashed stocks that survived and rebounded (IDEA, SUZLON, YESBANK) are present. A model that buys crashed, high-volatility
names (A07: +7.8 % 20-day net vs production +2.7 %, picks with a −29 % prior 3-month median return, 43 % under ₹50) is
flattered most by this.

Needed: a delisting-inclusive daily OHLCV source for NSE equities — candidates: NSE bhavcopy archives (daily all-stock
files, include later-delisted names), or a vendor history. Then re-run the day-TF arms on that universe; A07 stays
SUSPECT until then. A01's edge was checked to be robust to the obvious slices (≥ ₹50 only, ex its top-20 stocks) but is
also formally survivor-biased.
