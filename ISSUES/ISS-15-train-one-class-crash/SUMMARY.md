# ISS-15: LRExtrema `_train` can fit a one-class sample set and crash the solver

- **Area:** strategy training (`trader/strategies/lr_extrema.py::_train`)
- **Status:** PENDING — latent on HEAD (production feature/label config never hits it); fixed on research branch `exp/features` only
- **Source:** TD-018 campaign, 2026-10-18 (Stage B crash of EXP-06 / EXP-08)
- **Fix commits:** exp/features (research branch, not merged)
