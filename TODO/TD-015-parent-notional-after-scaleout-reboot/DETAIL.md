# TD-015: Persist the original parent notional

Source: ISS-03 guide (2026-10-17), "Out of scope" section. Verbatim; never delete.

---

> A position with NO add-ons that scales out and reboots re-seeds `last_lot_notional` from the reduced parent (`seed_position` uses `entry_price × remaining qty`), so its first later add-on is sized off the smaller remainder; memory keeps the original parent notional. Needs the original parent quantity persisted — tracked as TD-015.
