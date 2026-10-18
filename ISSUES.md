# Issues

One folder per reported problem under `ISSUES/ISS-NN-<slug>/` (SUMMARY · DETAIL verbatim · FIXED|PENDING marker). Open list: `ls ISSUES/*/PENDING`. IDs are permanent and never reused. A reported problem gets its folder before any fix.

| ID | Status | Area | Title |
|---|---|---|---|
| [ISS-01](ISSUES/ISS-01-scalein-pool-opening-cash-double-count/DETAIL.md) | FIXED (release-20261017c, pending field validation) | live capital / scale-in | Scale-in pool & effective capital use Kite opening cash — same-day restart double-counts buys |
| [ISS-02](ISSUES/ISS-02-rejected-addon-refires-every-candle/DETAIL.md) | FIXED via TD-001 (release-20261017d) | live orders / scale-in | Broker-rejected add-on is re-placed on every decision candle |
| [ISS-03](ISSUES/ISS-03-partial-scaleout-addon-restart-divergence/DETAIL.md) | FIXED 2026-10-17 | risk ledger / persistence | Partial scale-out on an add-on position: pro-rata in memory vs FIFO in DB — reboot changes avg entry, pool, loss-block arming |
| [ISS-04](ISSUES/ISS-04-cumulative-pnl-double-count/DETAIL.md) | FIXED (release-20261017d) | risk ledger / live capital | `capital_available` adds cumulative_pnl on top of Kite equity that already contains it |
| [ISS-05](ISSUES/ISS-05-loss-block-wall-clock-sessions/DETAIL.md) | PENDING | risk / scheduler | Loss block counts sessions by weekday wall clock, not the NSE trading calendar |
| [ISS-06](ISSUES/ISS-06-unfunded-pool-fallback-on-margins-failure/DETAIL.md) | PENDING | live capital / scale-in | Pool falls back to an unfunded 10% × base if Kite margins fail at boot and at 09:00 |
| [ISS-07](ISSUES/ISS-07-addon-fills-outside-normal-path/DETAIL.md) | PENDING | live orders / persistence | Add-on fills outside the normal path (pending at restart, fill while down, unknown order id, partial-then-cancel, no qty reconcile) |
| [ISS-08](ISSUES/ISS-08-manual-buy-recorded-as-addon/DETAIL.md) | PENDING | live orders | `_instrument_orders` fallback context: a manual BUY of a held symbol is recorded as an add-on lot |
| [ISS-09](ISSUES/ISS-09-loss-block-keys-resurrect-on-readd/DETAIL.md) | PENDING | persistence | Loss-block state keys of removed stocks survive and resurrect if the stock is re-added |
| [ISS-10](ISSUES/ISS-10-golden-parity-test-stale/DETAIL.md) | FIXED 2026-10-17 | tests | `test_parity_golden` / pipeline golden fails on clean HEAD |
| [ISS-11](ISSUES/ISS-11-health-strip-test-weekday-blind/DETAIL.md) | PENDING | dashboard / tests | `test_render_page_health_strip` fails 09:15–15:30 on any day incl. weekends — dashboard 'market open' check ignores weekday |
| [ISS-12](ISSUES/ISS-12-offgrid-15m-candles-on-ec2/DETAIL.md) | PENDING | data / historical fetch | Same-day re-warm-ups write off-grid '15minute' rows (15:16..15:25) into the EC2 candle cache |
| [ISS-13](ISSUES/ISS-13-broker-reject-entry-refire-loop/DETAIL.md) | PENDING | live orders | Broker-rejected ENTRY (insufficient funds) re-fires every candle |
| [ISS-14](ISSUES/ISS-14-backtest-trailing-ignores-candle-low/DETAIL.md) | FIXED 2026-10-18 (5970eb5) | backtest engine | Backtest trailing/breakeven exits ignore the candle low — live exits on intrabar pierces the backtest never sees |
| [ISS-15](ISSUES/ISS-15-train-one-class-crash/DETAIL.md) | PENDING (latent on HEAD; fixed on exp/features) | strategy training | `_train` guards total sample count only — a long-history feature pipeline can leave one class and crash the solver |
| [ISS-16](ISSUES/ISS-16-lab-universe-drops-hyphenated-symbols/DETAIL.md) | FIXED 2026-10-19 (37029f5) | Model Lab universe drops every hyphenated symbol (BAJAJ-AUTO …) |
