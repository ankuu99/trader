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
