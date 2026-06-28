"""Handoff: Gate A (fundamental) -> Gate B (trend, hard) -> trigger -> multiplicative rank."""

from trader.fvm import handoff


def _scores(**comp):
    return {s: {"composite": c, "pillars": {}, "factors": {}} for s, c in comp.items()}


def _tech(trend, timing):
    return {"trend_score": trend, "timing_score": timing,
            "technical_score": trend * timing, "extension_vetoed": False}


def test_gates_b_and_trigger_filter_the_pool():
    scores = _scores(GOOD=80, GOOD2=82, NOTREND=78, NOTRIGGER=76, VETOED=85, LOW=30)
    vetoes_map = {s: (True, []) for s in scores}
    vetoes_map["VETOED"] = (False, ["pledge_high_and_rising"])
    tech = {
        "GOOD": _tech(0.8, 0.6), "GOOD2": _tech(0.9, 0.7),
        "NOTREND": _tech(0.2, 0.6),     # fails Gate B (trend floor)
        "NOTRIGGER": _tech(0.8, 0.0),   # no trigger
        "VETOED": _tech(0.9, 0.9), "LOW": _tech(0.9, 0.9),
    }
    # pctile_cut=0 so Gate A is floor+veto only (isolates Gate-B / trigger behavior)
    cands, diag = handoff.select_candidates(scores, vetoes_map, tech, pctile_cut=0.0, floor=50)
    syms = [c["symbol"] for c in cands]
    assert syms == ["GOOD2", "GOOD"]                 # both pass; GOOD2 ranks higher
    assert cands[0]["final_rank"] > cands[1]["final_rank"]
    assert diag["VETOED"]["gate_a"] is False and diag["VETOED"]["veto_passed"] is False
    assert diag["LOW"]["gate_a"] is False            # below floor
    assert diag["NOTREND"]["gate_b"] is False
    assert diag["NOTRIGGER"]["trigger"] is False
    # final_rank = within-pool composite pctile × technical_score
    assert cands[0]["final_rank"] == handoff._pctile(
        {"GOOD": 80, "GOOD2": 82, "NOTREND": 78, "NOTRIGGER": 76})["GOOD2"] * (0.9 * 0.7)


def test_percentile_cut_admits_only_top_fraction():
    scores = _scores(A=90, B=80, C=70, D=60, E=50)   # 5 names
    vetoes_map = {s: (True, []) for s in scores}
    tech = {s: _tech(0.8, 0.6) for s in scores}
    cands, diag = handoff.select_candidates(scores, vetoes_map, tech, pctile_cut=0.70, floor=0)
    # top 30% by composite -> A (and B at the 0.70 boundary)
    passed = {s for s in scores if diag[s]["gate_a"]}
    assert "A" in passed and "E" not in passed and "C" not in passed


def test_regime_off_blocks_all_new_entries():
    scores = _scores(A=80, B=82)
    vetoes_map = {s: (True, []) for s in scores}
    tech = {s: _tech(0.9, 0.7) for s in scores}
    cands, _ = handoff.select_candidates(scores, vetoes_map, tech, regime_ok=False,
                                         pctile_cut=0.0, floor=50)
    assert cands == []
