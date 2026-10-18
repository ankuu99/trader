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

## Addendum 2026-10-18 (late) — probe and build started

Owner go-ahead ("Do all three"). Probe: NSE bhavcopy archives download with browser headers (old format to
2024-07-05, UDiFF after; 2008 files lack ISIN). Of the top-500 EQ names by traded value on 2012-01-02, **131 (26 %,
~10 % of traded value) no longer exist** (ISIN-issuer match vs 2026-10-16): JPASSOCIAT, RELCAPITAL, GITANJALI,
EDUCOMP, JETAIRWAYS, SINTEX, PUNJLLOYD, VIDEOIND, BHUSANSTL, HDFC, RANBAXY, SATYAMCOMP, … Split/bonus adjustment
from NSE's own adjusted PREVCLOSE on ex-dates. Build spec: `to_develop/2026-10-18_TD-022_L0c-nse-bhavcopy-day-source.md`
(new lab timeframe `dayn`). Found on the way: ISS-16 (lab universe drops hyphenated symbols such as BAJAJ-AUTO).

## Addendum 2026-10-19 — L0c first real run: validation FAIL, rework spec'd

Fetch/parse/build ran clean (4,635 daily files 2008→2026-10-16; 4,045 securities, 1,070 of them delisted), but the
adjusted series disagreed with Kite (median 3.1 % off; 40 % of days within 0.5 %). Cause: NSE bhavcopy's PREVCLOSE
is NOT adjusted on bonus/split ex-dates (RELIANCE 2017-09-07 and 2024-10-28 bonuses), and weekend special sessions
were not fetched. Rework (addendum in the L0c guide): adjustment factors from NSE's corporate-actions API (2008→,
includes delisted names; 1,280 bonus/split events), every calendar day fetched. `dayn` must not be used until the
re-validation passes.

## Addendum 2026-10-19 (later) — L0c signed off; survivorship-free `dayn` source available

Rework validated (completion record in `to_develop/completed/2026-10-18_TD-022_L0c-*`): 4,045 securities incl. 1,070
delisted, split/bonus adjusted from NSE corporate actions; daily returns agree with Kite on 99.3 % of days (level
offsets = Kite's recent dividend adjustments; the worst mismatches are Kite's own broken history). Next: ML-A01n /
ML-A11n and SN-1..3 (pre-registered) — then A07 un-SUSPECT or confirm.
