# ISS-09: Loss-block state keys of removed stocks survive and resurrect if the stock is re-added

Source: Independent production-safety review 2026-10-17, finding 9. Reproduced verbatim; dated addenda below. Never delete.

---

**9. LOW: blocks for removed stocks come back.** `load_loss_reentry` only reads watchlist stocks, so a removed stock's key stays in the DB and its old countdown returns if the stock is re-added.
