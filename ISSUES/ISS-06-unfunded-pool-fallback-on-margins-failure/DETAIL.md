# ISS-06: Pool falls back to an unfunded 10% × base if Kite margins fail at boot and at 09:00

Source: Independent production-safety review 2026-10-17, finding 6. Reproduced verbatim; dated addenda below. Never delete.

---

**6. LOW: if Kite margins fail at both boot and the 09:00 retry, the pool falls back to 10% of ₹6L = ₹60k of unfunded cash for the whole session.** (config.py `scale_in_budget`)
- Suggest `set_scale_in_budget(0)` at live boot, before the margins call.
- The margins call has never failed at boot since September (checked in the logs).
