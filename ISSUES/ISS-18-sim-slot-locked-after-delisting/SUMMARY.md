# ISS-18: portfolio simulator keeps a slot locked after a held stock stops trading

- **Area:** Model Lab strategy sims (TD-023 S0, `research/model_lab/portfolio.py::simulate`)
- **Status:** PENDING — found 2026-10-19; fix = DELIST exit at the last close once a held symbol has had no bar for N days
- **Source:** Main session, 2026-10-19 (SN-1..3 on the survivorship-free `dayn` source)
- **Fix commits:** —
