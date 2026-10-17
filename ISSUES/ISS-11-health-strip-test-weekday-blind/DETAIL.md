# ISS-11: `test_render_page_health_strip` fails 09:15–15:30 on any day incl. weekends — dashboard 'market open' check ignores weekday

Source: Session observation 2026-10-16 (test run during the reject-freeze fix). Reproduced verbatim; dated addenda below. Never delete.

---

`tests/test_ui_render_page.py::test_render_page_health_strip` fails whenever the local clock is between 09:15 and 15:30 IST, on any day of the week including Saturday/Sunday. Cause: the dashboard's market-open check ignores the weekday. Verified pre-existing at clean HEAD.
