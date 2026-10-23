"""
Vetoes (Phase 1) — binary disqualification gates, kept separate from the score so a
rejection is always inspectable (design Piece 4). These are the BACKTEST register
(4 hard vetoes + min-scoreability); the GSM/ASM compliance veto is LIVE-ONLY (§13c) and
provided separately via `is_compliance_flagged`.

check_vetoes() returns (passed: bool, reasons: list[str]). Thresholds are module constants
(tunable; v1 uses absolute ceilings — sector-adjusted D/E is a later refinement).

A veto firing on an OPEN position is also the rules-based Clock-1 thesis-break exit (§4a) —
the same register, reused at exit time.
"""

from trader.fvm import factors as fac
from trader.fvm import fields as F

# --- tunable thresholds ---
DE_CEILING = 2.0          # D/E above this ...
INT_COV_MIN = 1.5         # ... AND interest coverage below this  -> leverage veto
PLEDGE_HIGH = 20.0        # promoter pledge % above this AND rising -> pledge veto
MFG_REV_DROP = -5.0       # revenue YoY % below this ...
MFG_PROFIT_JUMP = 30.0    # ... AND profit YoY % above this  -> manufactured-earnings veto


def _latest(store, symbol, spec, asof, basis):
    return fac._latest(fac._series(store, symbol, spec, asof, basis))


def check_vetoes(store, symbol, asof, basis="consolidated") -> tuple[bool, list[str]]:
    reasons: list[str] = []

    # 1. CFO < 0 while net profit > 0  (earnings not converting to cash)
    cfo = _latest(store, symbol, F.CFO_A, asof, basis)
    npa = _latest(store, symbol, F.NET_PROFIT_A, asof, basis)
    if cfo is not None and npa is not None and cfo < 0 and npa > 0:
        reasons.append("cfo_negative_profit_positive")

    # 2. High leverage AND weak interest coverage
    de = _latest(store, symbol, F.DE_A, asof, basis)
    cov = _latest(store, symbol, F.INT_COVERAGE_A, asof, basis)
    if de is not None and cov is not None and de > DE_CEILING and cov < INT_COV_MIN:
        reasons.append("high_leverage_low_coverage")

    # 3. Promoter pledge high AND rising
    pv = [v for _, v in sorted(store.read_shareholding_asof(symbol, F.SH_PLEDGE, asof).items())
          if v is not None]
    if pv and pv[-1] > PLEDGE_HIGH:
        sl = fac.slope(pv[-4:])
        if sl is not None and sl > 0:
            reasons.append("pledge_high_and_rising")

    # 4. Manufactured earnings: revenue FALLING while profit jumps (the sign on revenue is
    #    the whole game — margin expansion on rising revenue must NOT trip this, §4b)
    rev_yoy = _latest(store, symbol, F.REVENUE_GROWTH_A, asof, basis)   # %
    nps = [v for _, v in fac._series(store, symbol, F.NET_PROFIT_A, asof, basis)]
    profit_yoy = ((nps[-1] - nps[-2]) / abs(nps[-2]) * 100.0
                  if len(nps) >= 2 and nps[-2] != 0 else None)
    if (rev_yoy is not None and profit_yoy is not None
            and rev_yoy < MFG_REV_DROP and profit_yoy > MFG_PROFIT_JUMP):
        reasons.append("manufactured_earnings")

    # 5. Min-scoreability: need core Pillar-1 growth + a Pillar-2 valuation anchor present
    #    (EV/EBITDA, since PEG/PE need price). Blocks a data-poor name scoring near median.
    p1_growth = fac.pillar1_factors(store, symbol, asof, basis)["yoy_profit_growth"]
    ev = _latest(store, symbol, F.EV_EBITDA_A, asof, basis)
    if p1_growth is None or ev is None:
        reasons.append("insufficient_data")

    return (len(reasons) == 0), reasons


def is_compliance_flagged(symbol: str, flagged: set[str]) -> bool:
    """LIVE-ONLY compliance veto (GSM/ASM/T2T). `flagged` from nse.fetch_compliance_flags().
    Backtest omits this (historical flag membership is patchy, §13c)."""
    return symbol.upper() in flagged
