# TD-020: News/no-news decline flag

Source: TD-018 campaign round 1, 2026-10-18 (`docs/02_Extrema_Literature_Review.md`, proposed arm 3). Never delete.

---

Hypothesis (Chan 2003; Jegadeesh et al.; Da, Liu & Schaumburg 2014): declines with no price-relevant corporate event
reverse, declines on news drift. It is the only untested campaign arm that brings information beyond the stock's own
price path about WHICH dip pays (round 1 showed own-path information is at chance, AUC ≈ 0.51).

Step 1 (probe, no code in trader/): stratify the Stage-A tradeable-trough truth by "corporate event inside the decline
window". Falsifier (pre-registered in docs/02): no-event vs event EV gap < 0.25 pp pooled, or sign inconsistent on
≥ ⅓ of stocks. Step 2 only if it passes: `features.news` add-on + live event feed.

Blocker: a point-in-time historical event table for the watchlist (2020→). Candidate sources to evaluate: NSE
corporate announcements / board-meeting archives, Trendlyne result calendars (see the Trendlyne notes in docs/), the
`qualify` skill's event-calendar sources.
