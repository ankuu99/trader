# ISS-16: A full EXIT while a scale-out sell is still pending is sized at the pre-partial quantity

Source: found by Claude in the live review of 26–30 Oct, 2026-10-31 (no owner report). Dated addenda below. Never delete.

---

## Evidence — THANGAMAYL, 2026-10-27 (EC2 journal, boot −4)

```
15:29:15 Candle | NSE:THANGAMAYL | ... | 2026-10-27 15:15:00          (pre-close flush, early-emitted last candle)
15:29:15 LR-Extrema EXIT (pattern-top scale-out 50%) | P(max)=0.867 >= 0.850 | gain=3.40% | held=43
15:29:15 Partial exit approved | x4 (frac=0.50) ; Live order placed x4 id=261027151552691
15:29:16 LR-Extrema TRAILING EOD CLOSE | price=4775.00 ; Exit approved | x8
15:29:16 ERROR Failed to place order: Insufficient stock holding or there are pending sell orders ... Order quantity: 8, Holding quantity: 4
15:29:17 EXIT order REJECTED — position state restored for retrigger
15:29:17 TRAILING EOD CLOSE x8 → same broker refusal, state restored again
15:29:18 Live fill | SELL x4 @ 4771.00 ; Partial close x4 of 8
15:29:20 TRAILING EOD CLOSE ; Exit approved x4 ; order placed ; 15:29:21 fill x4 @ 4771.00 ; Position closed
```

Net result was correct (8 bought 26 Oct, 4 + 4 sold, +₹1,256), but it took two broker refusals and finished 40 s before
the 15:30 CAS cutoff.

## Mechanism

1. The scale-out emission arms the remainder trail (`trailing_active`) on the 15m path.
2. The decision came from the 15:29:15 pre-close flush, which is after the 15:25 `exits.trailing.force_close_time`. So the
   very next tick satisfies the EOD force-close in `extrema_exit.py` (~l.420) and emits a full EXIT.
3. `RiskManager._validate_exit` sizes a full exit from `_open_positions[inst]`, which is reduced only when the partial
   FILLS (`reduce_position`). While the partial SELL is pending it still reads the pre-partial quantity (8).
4. Kite refuses a sell larger than the holding minus pending sells. The REJECTED restore path re-arms the EOD close, which
   retries on each tick until the partial fill lands. Then the quantity is right and the close goes through.

## Exposure

- Any 15m-regime position (force_close_time 15:25) whose pattern-top scale-out is decided by the pre-close flush (15:29:15).
  The same race applies to any full exit emitted while a partial sell is in flight (trailing / stale / hard stop on a tick
  between partial placement and fill), but the EOD case is the deterministic one.
- If the partial fill postback arrives after 15:30, every retry is refused (CAS) and the remainder is held overnight against
  the EOD-close intent. Each refusal also goes through the broker-reject path (signal row flipped to `BROKER:`).

## Fix options (owner decides; none chosen)

- (a) `_validate_exit`: subtract pending partial-exit quantity from a full exit (track pending sell qty per instrument).
- (b) Strategy: suppress any new exit while a partial EXIT is pending (it already holds a snapshot for the partial).
- (c) Skip the scale-out when the decision is past `force_close_time` and emit the full EOD close directly. That is what
  happens in effect anyway.
