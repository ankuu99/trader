# ISS-18: portfolio simulator keeps a slot locked after a held stock stops trading

## Report (main session, 2026-10-19)

Exits are evaluated only on bars of the held symbol. When a symbol's data ends (delisting, merger, suspension), a
position in it stays open until the end of the whole simulation, then closes at the symbol's last close ("END"),
holding one of the 15 slots for years. Pending entries on such a symbol would never fill either. This never happened on
the survivor-only `day` source. On `dayn` (SN-1..3) it hits 0–3 positions per sim, locking 3–27 slot-years out of about
230 (CAIRN, HDFC, DISHMAN, MAYTASINFR, SATYAMCOMP, PEL, …), in models and coin controls alike.

## Proposed fix
Once the simulation date passes a held symbol's last bar by more than `delist_grace_days` (default 7 calendar days),
close the position at that last close with reason "DELIST" and drop any pending entry on that symbol. The proceeds
equal the last traded price: right for cash mergers, optimistic for suspensions that never resume (noted as a caveat).
