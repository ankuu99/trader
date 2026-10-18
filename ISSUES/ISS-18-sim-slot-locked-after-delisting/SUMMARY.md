# ISS-18: portfolio simulator keeps a slot locked after a held stock stops trading

- **Area:** Model Lab strategy sims (TD-023 S0, `research/model_lab/portfolio.py::simulate`)
- **Status:** FIXED 2026-10-19 (7c9b45c) — `SimSpec.delist_grace_days=7`: a held symbol whose data ended > 7 days ago closes at its last close (reason DELIST), pending/queued entries dropped
- **Source:** Main session, 2026-10-19 (SN-1..3 on the survivorship-free `dayn` source)
- **Fix commits:** 7c9b45c
