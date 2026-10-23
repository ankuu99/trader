# TD-021: Model Lab — vanilla turning-point framework outside LR-Extrema

Source: owner, 2026-10-18, verbatim:

> are we saying that there exists no strategy or model that would beat this current model? I dont think that is true.
> especially when we say that the model is equivalent to tossing a coin. i think we are tryig to stay to the construct
> of lr extrema, which is why we are bound and not able to to imrpvoe on anything. few nomenclatur, model is the
> underlying mathematical and ml based tool that decides whether a given candle isa goodentry/exit poitn or not.
> dstrategy is everything around stop loss, risk maangement, min exit, early exit, target profit etc. what I woudl
> suggest it create a vanialla framework, that only utilizes the current framework to get the stock related
> information. then the model improvement plan shoudl simply treat those as time series data points (for one stock,
> volume, price, start/close, days min/ days max, etc, everything is a time series data, we can come up with so many
> more factors for a given candle and everything individually becoimes a time series), and see if it is able to find
> the local min or max, (with abiltiy to train on historical data (some precentage of over all time series) and then
> predict on the remaining treating that as future point by point evolution of the time series. that's what we need to
> do. also, the aim is to predict whether a given candle isa potential min or not and whether the future woudl result
> into a potential change in direction and by how much.

Proposal: `docs/03_Model_Lab_Proposal.md`.

## Addendum 2026-10-18 — owner answers (verbatim)

> few poitners for the data, you are free to pull latest fresh data from kite using the standard authetnication
> mechianm as and when required. predict forward need not be just oe candle at a time, after all that also woudl
> determine the hold period, potential. coming to quesitons, all stocks are canddiates. all time frames. both for min.
> date splits need to be dyanmic, dont just stick to one. also, a lot methodligcally would have changed year on year.
> you are free t isntall torch locally. document all this. as i intend to start ina new session.

Recorded as decisions D1–D9 in `docs/03_Model_Lab_Proposal.md` § "Owner decisions"; scope approved, build starts in a
new session at § "Start here". torch 2.14.1 installed in `.venv` (MPS available), listed in `requirements-lab.txt`;
full pytest green after install (582 passed).
