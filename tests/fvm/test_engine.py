"""Backtest engine: entry/hold/exit/P&L loop + triple-barrier labels."""

import pandas as pd

from trader.fvm import engine, labels


def _daily(closes):
    ts = pd.bdate_range("2023-01-02", periods=len(closes))
    return pd.DataFrame({"timestamp": ts, "open": closes,
                         "high": [c * 1.002 for c in closes],
                         "low": [c * 0.998 for c in closes],
                         "close": closes, "volume": [1000.0] * len(closes)})


def test_engine_enters_winner_skips_downtrend(monkeypatch):
    winner = _daily([100 + 0.3 * i for i in range(150)])   # steady riser (~144 at end)
    skip = _daily([50.0] * 150)
    price_data = {"WINNER": winner, "SKIP": skip}
    sectors = {"WINNER": "Tech", "SKIP": "Tech"}

    def fake_eval(df):
        last = float(df["close"].iloc[-1])
        if last > 60:   # WINNER -> a clean candidate
            return {"trend_score": 0.8, "timing_score": 0.6, "technical_score": 0.48,
                    "extension_vetoed": False, "initial_stop": last * 0.85,
                    "pullback": 0.6, "breakout": 0.0}
        return {"trend_score": 0.1, "timing_score": 0.0, "technical_score": 0.0,
                "extension_vetoed": False, "initial_stop": None, "pullback": 0.0, "breakout": 0.0}

    monkeypatch.setattr(engine.technical, "evaluate", fake_eval)
    res = engine.run_backtest(
        store=None, price_data=price_data, sectors=sectors, sleeve_capital=1_000_000,
        score_fn=lambda st, uni, a: {s: {"composite": 80, "pillars": {}, "factors": {}} for s in uni},
        veto_fn=lambda st, s, a: (True, []),
        select_kwargs={"pctile_cut": 0.0, "floor": 50},   # tiny test universe -> relax pctile gate
    )
    syms = {t["symbol"] for t in res["trades"]}
    assert "WINNER" in syms and "SKIP" not in syms
    win = [t for t in res["trades"] if t["symbol"] == "WINNER"][0]
    assert win["pnl"] > 0                      # rode the uptrend
    assert res["final_equity"] > 1_000_000     # net profit after costs
    m = engine.compute_metrics(res["trades"], 1_000_000)
    assert m["trades"] >= 1 and m["return_pct"] > 0


def test_engine_respects_capital_no_negative_cash(monkeypatch):
    price_data = {f"S{i}": _daily([100 + 0.2 * j for j in range(150)]) for i in range(20)}
    sectors = {s: f"sec{i % 6}" for i, s in enumerate(price_data)}
    monkeypatch.setattr(engine.technical, "evaluate",
                        lambda df: {"trend_score": 0.8, "timing_score": 0.6, "technical_score": 0.48,
                                    "extension_vetoed": False,
                                    "initial_stop": float(df["close"].iloc[-1]) * 0.9})
    res = engine.run_backtest(
        store=None, price_data=price_data, sectors=sectors, sleeve_capital=500_000,
        score_fn=lambda st, uni, a: {s: {"composite": 80, "pillars": {}, "factors": {}} for s in uni},
        veto_fn=lambda st, s, a: (True, []),
        select_kwargs={"pctile_cut": 0.0, "floor": 50})
    assert len(res["trades"]) > 0                          # entries actually happened
    # never over-deploys: every recorded equity point is finite & positive
    assert all(eq > 0 for _, eq in res["equity_curve"])
    assert res["final_equity"] > 0


def test_triple_barrier_upper_lower_time():
    rising = _daily([100 + i for i in range(20)])
    assert labels.triple_barrier_label(rising, 0, atr_val=2.0, k=2.0) > 0     # upper hit
    falling = _daily([100 - i for i in range(20)])
    assert labels.triple_barrier_label(falling, 0, atr_val=2.0, k=2.0) < 0    # lower hit
    flat = _daily([100.0] * 20)
    assert labels.triple_barrier_label(flat, 0, atr_val=5.0, k=2.0) == 0.0    # time barrier
