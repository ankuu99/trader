# ISS-08: `_instrument_orders` fallback context: a manual BUY of a held symbol is recorded as an add-on lot

Source: Independent production-safety review 2026-10-17, finding 8. Reproduced verbatim; dated addenda below. Never delete.

---

**8. LOW: `_instrument_orders` keeps the add-on order as the fallback context** (orders/manager.py:327-328). A manual BUY of a held symbol would be recorded as an add-on lot.
