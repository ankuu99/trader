# ISS-13: Broker-rejected ENTRY (insufficient funds) re-fires every candle

Source: `todo.md`, as of 2026-10-17. Reproduced verbatim; dated addenda below. Never delete.

---

- **Freeze entry guard on broker insufficient-funds rejects** — an exchange-REJECTED
  entry logs "clearing entry guard" and re-fires every candle (STYLAMIND July: dozens;
  KPL 2026-08-07: ×2). The reject→re-fire fix only froze the guard for PRE-order
  rejects; extend the same session-freeze to broker rejections (at minimum for
  insufficient-funds, where retrying without new cash is guaranteed futile).

## Addendum 2026-10-17

Mitigated by TD-001 (pre-order cash check): insufficient-funds orders are no longer sent, so they cannot be broker-rejected and re-fired. Other broker reject reasons still re-fire every candle — by the owner's 2026-10-17 stance (do not block while the model is bullish).
