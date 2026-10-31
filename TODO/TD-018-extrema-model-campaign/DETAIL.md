# TD-018: Trough/peak model evaluation campaign

Source: owner, 2026-10-18. Verbatim; never delete.

---

> okay with all the framework level fixes done, we are in a very good state now. i want to revist the model for detecting the troughs and peaks.

> Hell me understand what i need to read to better gfigure out a kodel that identifies the peaks and troughs better. Roght now if you look at the trades happening, we sre actually missing really good troughs as entries

> Yes, and after that i want uou to start multiple eorktrees to evaluatd all these and see if we gather any peformance gains, separately i also wsmy hou yo refer the quoted literature above.
> As you can see a lot of research and trial has been done in the past. But bow we need to ensure persistent documentation to see what all paths were taken and then evaluate. Trll mr a plan before starting anything, i will review

> Fix the 14 then go agead with this plan. Continue autonomously now.

Plan (as proposed and approved 2026-10-18): `docs/01_Extrema_Model_Campaign.md`. Ledger:
`reviews/extrema_campaign/LEDGER.md`. Open owner decisions answered by default (owner said "go ahead"): losing arms
stay on `exp/*` branches; pass thresholds as proposed; no extra hand labels.

## Addendum 2026-10-18 — round 1 complete

Twelve detection arms fail Stage A; production P(min) median AUC 0.511 vs tradeable troughs; prior-day India VIX percentile is the only robust signal (median AUC 0.638, 6/7 years) but the decision-layer arm (EXP-18) did not survive its plateau check. Summary: `reviews/extrema_campaign/CAMPAIGN_ROUND1_20261018.md`; every path: `reviews/extrema_campaign/LEDGER.md`. Code of losing arms on `exp/labels`, `exp/features`, `exp/rules`, `exp/regime`.
