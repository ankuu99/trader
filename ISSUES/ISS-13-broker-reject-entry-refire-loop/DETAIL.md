# ISS-13: Broker-rejected ENTRY (insufficient funds) re-fires every candle

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

- **Freeze entry guard on broker insufficient-funds rejects** — an exchange-REJECTED
  entry logs "clearing entry guard" and re-fires every candle (STYLAMIND July: dozens;
  KPL 2026-08-07: ×2). The reject→re-fire fix only froze the guard for PRE-order
  rejects; extend the same session-freeze to broker rejections (at minimum for
  insufficient-funds, where retrying without new cash is guaranteed futile).
