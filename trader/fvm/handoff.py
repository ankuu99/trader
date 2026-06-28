"""
The handoff (design Piece 6) — fundamentals GATE, technicals TIME, rank multiplicatively.

select_candidates() composes the three layers into ranked entry candidates:

  Gate A  (fundamental eligibility): composite pctile ≥ cut  AND  composite ≥ floor
                                     AND passes vetoes
  Gate B  (technical trend, HARD):   trend_score ≥ floor      (never buy counter-trend)
  Trigger (event-driven):            timing_score > 0          (fresh pullback/breakout)
  Rank:                              within-eligible-pool composite-pctile × technical_score
  Regime throttle (§11a):            risk-off ⇒ no NEW entries (existing positions unaffected)

Returns (candidates, diagnostics): candidates sorted by final rank desc; diagnostics records
each symbol's gate decisions (design wants every rejection inspectable).
"""

COMPOSITE_PCTILE_CUT = 0.70     # top 30%
COMPOSITE_FLOOR = 50.0          # absolute floor (hybrid gate, §6a)
TREND_FLOOR = 0.40             # Gate-B Trend_Score floor


def _pctile(vmap: dict[str, float]) -> dict[str, float]:
    """Mid-rank percentile in [0,1] (higher value -> higher pctile)."""
    if not vmap:
        return {}
    vals = sorted(vmap.values())
    n = len(vals)
    out = {}
    for k, v in vmap.items():
        below = sum(1 for x in vals if x < v)
        equal = sum(1 for x in vals if x == v)
        out[k] = (below + 0.5 * equal) / n
    return out


def select_candidates(scores: dict, vetoes_map: dict, tech_map: dict,
                      regime_ok: bool = True,
                      pctile_cut: float = COMPOSITE_PCTILE_CUT,
                      floor: float = COMPOSITE_FLOOR,
                      trend_floor: float = TREND_FLOOR):
    """
    scores:      {sym: {"composite", "pillars", "factors"}}  (scoring.compute_scores)
    vetoes_map:  {sym: (passed: bool, reasons: list)}        (vetoes.check_vetoes)
    tech_map:    {sym: {"trend_score","timing_score","technical_score","extension_vetoed"}}
    """
    comp = {s: scores[s]["composite"] for s in scores}
    pct = _pctile(comp)
    diagnostics: dict[str, dict] = {}

    # Gate A
    pool = []
    for s in scores:
        passed_veto, reasons = vetoes_map.get(s, (True, []))
        gate_a = (pct[s] >= pctile_cut) and (comp[s] >= floor) and passed_veto
        diagnostics[s] = {
            "composite": comp[s], "composite_pctile": pct[s],
            "gate_a": gate_a, "veto_passed": passed_veto, "veto_reasons": reasons,
        }
        if gate_a:
            pool.append(s)

    # within-eligible-pool fundamental percentile (for the rank term)
    pool_pct = _pctile({s: comp[s] for s in pool})

    candidates = []
    for s in pool:
        t = tech_map.get(s, {})
        trend = t.get("trend_score", 0.0)
        timing = t.get("timing_score", 0.0)
        gate_b = trend >= trend_floor
        trigger = timing > 0.0
        d = diagnostics[s]
        d.update({"gate_b": gate_b, "trend_score": trend, "trigger": trigger,
                  "timing_score": timing})
        if gate_b and trigger and regime_ok:
            final = pool_pct[s] * t.get("technical_score", trend * timing)
            d["final_rank"] = final
            candidates.append({
                "symbol": s, "final_rank": final,
                "composite": comp[s], "pool_pctile": pool_pct[s],
                "trend_score": trend, "timing_score": timing,
                "technical_score": t.get("technical_score", trend * timing),
            })
    candidates.sort(key=lambda c: -c["final_rank"])
    return candidates, diagnostics
