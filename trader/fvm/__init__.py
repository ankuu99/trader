"""Fundamentally-Validated Momentum (FVM) strategy package.

Self-contained home for the FVM strategy. Reuses the generic core in `trader/`
(auth, Store for candles, costs, scheduler, RiskManager/OrderManager, Strategy/Signal
base) by import; adds FVM-specific data (PIT fundamentals), factors, scoring, technical
layer, a positional backtest engine, and a sleeve risk path. LRExtrema is untouched.

See docs/FVM_Design_Decisions.md and docs/FVM_Implementation_Plan.md.
"""
