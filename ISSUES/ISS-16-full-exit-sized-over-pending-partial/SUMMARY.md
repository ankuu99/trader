# ISS-16: A full EXIT while a scale-out sell is still pending is sized at the pre-partial quantity → broker rejects

- **Area:** live orders / exits (`trader/risk/manager.py::_validate_exit`, `trader/policy/extrema_exit.py` EOD close)
- **Status:** PENDING — observed live 2026-10-27 (THANGAMAYL); outcome correct by timing, no fix decided
- **Source:** weekly live review 2026-10-31 (`reviews/market_drawdown_20261022.md`, addendum 2026-10-31)
- **Fix commits:** —
