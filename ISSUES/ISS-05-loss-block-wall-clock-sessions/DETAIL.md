# ISS-05: Loss block counts sessions by weekday wall clock, not the NSE trading calendar

Source: Independent production-safety review 2026-10-17, finding 5. Reproduced verbatim; dated addenda below. Never delete.

---

**5. LOW-MEDIUM: the loss block counts sessions with a wall clock, not a trading calendar.**
- The scheduler and the box both run Mon–Fri with no holiday list. On 2026-10-02 (an NSE holiday) post_market ran and logged "Risk manager daily reset" (verified). Each weekday holiday therefore makes the block one trading session shorter than in the backtest.
- The opposite happens on a trading day where post_market never runs (crash through 15:35, box down). The block then lasts one session longer.
- A 15m exit on the 15:15 candle fills the next morning in the backtest but the same day live, so live is one more session shorter in that case.
- Otherwise the "earliest re-entry is D+3" rule matches `engine.reset_day`.
