# TD-023: Strategy framework for Model Lab models

## Report (owner, 2026-10-18, verbatim)

> while these are runing ,can we start on the strategy framework aroud this, what would that look like? ahve we
> thought of it yet? will these be baked into current framework? should we braistom on that or it is of no use utill
> we get a stable model ?

> day and 15 min both. whoele universe, with exclusion lists on really bad stocks, this list could be reviesed. first
> it will run on its own with its own capital, then depdending on performance we can switch off lR extrema or this one
> ain a few months.

## Notes

Design: `docs/04_Strategy_Framework_Proposal.md` — new decision layer (pooled model, daily cross-sectional ranking,
slots, exit library) on the existing execution body (Kite/risk/orders/CAS/persistence). Framework built now,
model-agnostic; tuning waits for a frozen model. ₹ results depend on TD-022 (survivorship). Live open questions: two
sleeves on one Kite account (ownership of overlapping holdings), 15m whole-universe compute budget on the t2.micro,
paper period, dated switch-off review.
