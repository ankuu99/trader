# TD-019: Signal.size_weight is applied before the per-stock capital cap

Source: discovered 2026-10-18 during TD-018 (EXP-18c). Never delete.

---

`RiskManager.validate` (`trader/risk/manager.py` ~L335–345) computes `quantity = max_risk_per_trade // sl_distance`,
multiplies it by `signal.size_weight`, and only THEN caps by `max_capital_per_stock`. With the 20 % hard stop the
risk-based quantity is far above the capital cap, so any size_weight that leaves it above the cap changes nothing.
EXP-18c (calm-regime size ×0.5) produced a FULL-window backtest identical to the rupee. The same applies to the
meta-labeling confidence sizing (`meta_label.sizing`) — its historical results may have been partly inert.

Options (owner to decide; none applied): apply size_weight after the capital cap (a behaviour change for anything that
sets it), or express sizing as a fraction of the capped notional. Any campaign arm that sizes positions must account
for this.
