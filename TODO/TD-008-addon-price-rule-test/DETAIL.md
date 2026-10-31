# TD-008: Test: add-on only when price is below the original / previous buy

Source: Owner, 2026-10-17 (session). Reproduced verbatim; dated addenda below. Never delete.

---

> one thing that i would liek to further add to the scale in, if it is not already there, is that the scale in should happen if the new entry price is lower that nthe original, and same ofr hte subsequent ones. that way any false positive from the mode will also get rejected. let's discuss this after doing the analysis. no change requried as of now.

> not that you have put that in words, i think it wont realy make sense, but worth testing out. reason being, if the stock is actually goign to fall, we are buying a falling knife, and if the stock is actually going up, we are going to miss out on slightly more buy ins. the only case where this would be helpful is when a stock rebounds within the window and none of hte stale exits apr the loss maker actually gets hit during that iwndow. else it would jsut make loss.

Variants under test vs released scale-in + loss block (3 sessions): `below_entry` (below the parent entry), `below_last` (below the previous buy), `band4` (0–4% below the previous buy). 14 windows 2020→2026.

## Addendum 2026-10-17 — result

FALSIFIED. Full 2020→2026 Δ vs released: below entry −₹113.6k, below last buy −₹110.2k, 0–4% band −₹136.6k; DD 36.8% → 37.4–37.8%; years beaten 2/7, 2/7, 1/7. Full table: `reviews/addon_price_rule_20261017.md`. No repo change.
