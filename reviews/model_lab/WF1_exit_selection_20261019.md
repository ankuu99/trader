# WF-1 — would the "best" hold/exit settings have been chosen without hindsight?

Run 2026-10-19 (main session, autonomous; informational, post-hoc on existing sims — no new simulations).

**Question.** SC2/SC3 picked the best hold/exit for each score by looking at 2011–2026 as a whole, for example the
production ranker's ₹14.6 L with a +20 % target. Suppose the settings were instead picked each year using only the
years before it. How much of that survives?

**Method.**
- **Candidate settings** for each score, all day bars with the best 2 a day, ₹6L and 15 × ₹40k:
  - SC2 holds of 5/10/20/40/60 days with no other exit;
  - SC3 P60 exits x1–x6: stop −20 %, stop −10 %, trail 10 % after +10 %, trail 15 % after +10 %, target +20 %, and
    stop −20 % + trail.
- **Yearly pick:** for each year Y from 2013, pick the setting with the best record over all years before Y, by two
  criteria:
  - total ₹;
  - "Calmar" = total ₹ ÷ worst single-year drawdown %.
- **Score:** add up the picked setting's year-Y ₹.
- **Approximation:** yearly ₹ are taken from the full-period runs. A real switch at New Year would differ slightly
  (positions open across the boundary, different capital path).

| Score | Walk-forward pick by ₹ | by Calmar | Hindsight best (2013–26) | Median setting | Worst setting |
|---|---|---|---|---|---|
| Production ranker (prod P(min) replay) | ₹9.90 L | **₹13.34 L** | ₹14.54 L (hold 60, target +20 %) | ₹11.89 L | ₹5.49 L |
| A01 | ₹7.06 L | ₹5.89 L | ₹9.98 L (hold 60, stop −20 %) | ₹8.52 L | −₹0.64 L |

Picks:
- **Production ranker by Calmar:** trail 15 % in 2013, then **hold 60 + target +20 % in every year from 2014**.
- **Production ranker by ₹:** wanders to hold 40 for 2015–17.
- **A01:** wanders between hold 10/20, stop −10 % and stop −20 % under both criteria.

**Read-out.**
- For the production ranker, "hold up to 60 days, take +20 %" is the choice a risk-adjusted rule would have made from
  2014 on, using only the past. Most of its ₹14.5 L is not exit-overfitting: the walk-forward version gets ₹13.3 L.
  This is still on the survivor-only `day` universe; SN-2 repeats it on `dayn`.
- For A01, choosing exits from the past does **worse than a typical fixed setting**. The exit choice is noise there,
  so A01 should run on a plain fixed setting (hold 20, as in SC2) rather than a tuned exit.
- This does not change SC6. Neither beats the full production system on 2025–26.
