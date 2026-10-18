# ISS-16: Model Lab universe drops every symbol containing a hyphen

## Report (main session, 2026-10-18)

While probing NSE bhavcopy archives for TD-022, BAJAJ-AUTO (top-10 by traded value in 2012) was missing from the
lab's daily bars. Cause: `snapshot_instruments` skips any Kite NSE EQ instrument whose tradingsymbol contains "-"
(`... or "-" in ts: continue`). The intent was to drop series-suffixed instruments (e.g. `XYZ-BE`, `XYZ-SM`, rights
`-RE`, bonds `-N1`), but it also drops real equity symbols with a hyphen in the name (BAJAJ-AUTO, and any other
hyphenated EQ ticker). Every lab run so far (A01–A11, S0/SC sims) is missing these names on both day and 15m.

## Proposed fix
Drop only when the part after the last "-" is a series/instrument code (BE, BZ, BL, SM, ST, RE, RR, IL, IT, GB, GS,
IV, MF, or a letter followed by digits such as N1/Y3/E1); keep the rest. Snapshot again, fetch the newly included
names (day from 2008, 15m for the PIT intraday list), rebuild the liquidity panel. The TD-022 NSE-bhavcopy source
includes hyphenated names natively, so a model re-run on that source is not affected.

## Addendum 2026-10-19 — fixed (main session)

Probe of Kite `instruments("NSE")` (EQ, segment NSE): 7,189 hyphenated tradingsymbols; the part after the last "-"
is a 2-character code (SG, N0–N9, NA–NS, SM, BE, GS, ST, TB, SF, GB, BZ, IV, RR, RL, …) for all but a handful.
Rule implemented: drop iff the suffix is exactly 2 characters. The fresh snapshot keeps 7 real names: BAJAJ-AUTO,
NAM-INDIA, HCL-INSYS, BOSCH-HCIL, UMIYA-MRO, and the class-B listings KLBRENG-B, MCCHRLS-B (1-char suffix, listed
2026-04). Day bars fetched for all 7 (BAJAJ-AUTO from 2008-05-26), 15m for BAJAJ-AUTO (2015-02) and NAM-INDIA
(2017-11); `liquidity_daily.parquet` rebuilt (pre-fix copy kept in the session scratchpad). PIT top-200 membership
gained: BAJAJ-AUTO every year 2010–2026, NAM-INDIA 2020–21, HCL-INSYS 2015–17, BOSCH-HCIL 2016. Runs made before
the fix are not re-run: one name in ~200 per year; the TD-022 `dayn` source includes these names natively and is
the basis for the next runs.
