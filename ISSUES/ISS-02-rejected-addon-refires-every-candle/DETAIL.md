# ISS-02: Broker-rejected add-on is re-placed on every decision candle

Source: Independent production-safety review 2026-10-17, finding 2. Reproduced verbatim; dated addenda below. Never delete.

---

**2. MEDIUM: a broker-rejected add-on is re-placed on every decision candle.** (risk/manager.py:384-475, lr_extrema.py:289-306)
- Add-on signals carry no state. After a REJECTED, `on_order_cancelled` frees the pending lock, and the spacing and tier checks still pass.
- So a new add-on order goes out every 15m bar while P(min) stays above threshold, with a Telegram reject alert each time.
- Insufficient-funds rejects (#1, #3, #6) trigger this directly.
- Suggest: after a broker reject, set `last_invest_date` to today or mark the add-on blocked. Confidence: verified by reading.

## Addendum 2026-10-17 — owner position

> 2 note it was tried, but dont block, given the model continues to remain bullish on that. let;s discuss this beofre we dicde

Related: ISS-13 (same loop for parent entries), TD-001 (pre-order real-margin check).
