# ISS-07: Add-on fills outside the normal path (pending at restart, fill while down, unknown order id, partial-then-cancel, no qty reconcile)

Source: Independent production-safety review 2026-10-17, finding 7. Reproduced verbatim; dated addenda below. Never delete.

---

**7. LOW: add-on fills that arrive outside the normal path.**
- **Pending at restart:** a pending add-on order is not re-locked, because main.py:468 skips held instruments.
- **Fill while down:** that fill is never delivered, so the DB misses the lot. A full exit then sells only what the DB holds and leaves orphan shares, and the next signal can place a second add-on.
- **Unknown order ID:** a fill that arrives later with an unknown order ID is booked as a *parent* BUY. That overwrites the position quantity and entry price.
- **Partial fill then CANCELLED:** the filled quantity is ignored.
- **No quantity check:** startup and post-market only check whether a holding exists, never its quantity. A mismatch is never detected, and if the DB holds more than Kite, the exit SELL is rejected in a loop.
- All of this needs a seconds-long window with MARKET orders, and most of it existed before for parent orders.
