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
