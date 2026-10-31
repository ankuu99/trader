# Trough/peak model campaign — round 1 result (2026-10-18)

Owner question: *"we are actually missing really good troughs as entries"* → revisit the detection model, evaluate
every path built on other branches and in the literature, with persistent documentation. Protocol
`docs/01_Extrema_Model_Campaign.md` (pre-registered, DECISIONS 2026-10-18); every path in
`reviews/extrema_campaign/LEDGER.md` (R-, B-, EXP- rows); literature `docs/02_Extrema_Literature_Review.md`.

## Bottom line

1. **No detection change improves on the production model.** Twelve arms (labels, features, rules, models) all fail
   Stage A. Not one ranks "troughs that pay under our exits" meaningfully better than today's P(min). After Stage A was
   demoted (see the addendum below), all twelve were also run through the full Stage-B backtest, and **all twelve fail
   on money too**.
2. **But today's P(min) doesn't rank them either** (median AUC 0.511). Nor does any single own-price measure (best
   0.534). Whether a dip pays is almost unpredictable from the stock's own price path. The strategy earns from its
   exits and from *when* it happens to trade, not from picking better dips. "Missing good troughs" is real, but no
   available price-shape model finds them reliably ahead of time.
3. **The one real signal is market timing.** The prior-day India VIX level (vs its trailing year) ranks tradeable
   troughs at median AUC 0.638 (86 % of stocks), stable in 6/7 calendar years 2020–26. Baseline positions opened in
   the VIX "stress" third average +1.34 % vs +0.66 % in the "calm" third, and stress beat calm in 7/7 years.
4. **Turning that into P&L didn't survive the protocol.**
   - Taking *more* entries under stress (lower threshold) adds weak marginal entries and loses in crashes (HORIZON
     −₹216k to −₹293k).
   - Blocking calm entries throws away ₹415k of 2020–26 profit.
   - Being pickier in calm (threshold +0.02…+0.05) consistently lowers drawdown (HORIZON DD −2.4…−2.8 pp) but its P&L
     effect flips sign between windows. +0.03 passed, its neighbours did not → not a plateau → not adopted.
   - Downsizing calm entries is inert because of a sizing-order quirk (TD-019).

## Baseline changes made along the way

- **ISS-14 fixed** (5970eb5): the backtest ignored candle lows for trailing/breakeven exits. The new baseline is FULL
  2025-01 → 2026-10-16 ₹439.2k / DD 5.8 % / Calmar 6.18 (was ₹465.4k / 6.60). HORIZON is ₹2,019k (was ₹1,918k).
- **Nifty 50 + India VIX 15m history** backfilled 2019-06 → 2026-10-16 in the local cache.
- Reusable tooling on the main line: `scripts/campaign/` (window runner, Stage-A scorer, probes, batch runners),
  `trader/policy/outcome.py` (shared exit-outcome simulator), and `trader/features/addons.py` (default-off add-on + lag
  framework).

## What each family taught us (detail in the ledger)

| Family | Arms | Result | Lesson |
|---|---|---|---|
| Outcome-aligned labels | EXP-01, EXP-02 (+ forward_label EXP-03) | worse (ΔAUC −0.013 / −0.072) | Too few paying dips per training window; the model overfits them. The campaign's starting hypothesis is retired. |
| Own-price features | EXP-04 lags, -05 bar shape, -06 ATR distance, -08 S/R, -10b OU | ≈ 0 or worse | Matches the headroom probe: own-path shape carries no information about payoff. |
| No-ML rules | EXP-09a, -09b, -10a | worse than the model | The model's capitulation-bar bias still beats RSI / lowest-turn / OU rules. |
| Market context as features | EXP-07 | +0.010 ΔAUC (only positive arm), fails gate | The signal is real, but a per-stock model with a 7-week 15m window can't learn a slow market variable. |
| Market context at the decision layer | EXP-18a–f, 18d2/18d5 | no robust pass | Timing information exists at the bar level; the marginal trades it adds or removes don't convert consistently. |
| Probes | EXP-12/12b/12c/12d/13/14 | VIX: robust signal; residual OU, volume: null | — |

## Where the code lives

Losing arms stay on pushed branches, not on the main line (owner default 2026-10-18):

- `exp/labels` @ b99bfce: `labels.type: tradeable`
- `exp/features` @ d54a0c0: bar_shape / atr_dist / sr / market add-ons
- `exp/rules` @ abd3233: rules pipeline, passthrough model, OU
- `exp/regime` @ 4c0a1c0: `market_regime` entry modulation + engine VIX-percentile injection

## Open follow-ups (owner decides)

- **TD-020 — news/no-news decline flag** (EXP-15, Chan 2003). This is the one literature arm that brings *new*
  information about which dip pays. It needs point-in-time corporate-event history (results dates, board meetings,
  rating actions); blocked until a source is confirmed.
- **TD-019 — size_weight before the capital cap.** Fix it if any sizing idea (incl. a calm-regime downsizing retry) is
  to be tested.
- **Optional defensive overlay:** calm-regime threshold +0.02…+0.05 reliably trims crash drawdown (−2.4…−2.8 pp
  HORIZON) at uncertain P&L cost, like the other defensive-only options in CLAUDE.md. It would need live VIX wiring
  (daily India VIX at pre-market) and owner sign-off. Not recommended on current evidence.
- If detection is revisited: a model that pools across stocks (outside today's per-stock contract, see the inventory
  §1) is the only remaining structural lever for slow variables like market state. That is a refactor, not a config
  arm.


## Addendum 2026-10-18 — controls and Stage B of every arm

- **Coin-flip control (EXP-20):** random entries/tops at the bot's own firing rates make money on these names
  (FULL ₹158–389k) because the watchlist was picked with hindsight and the exits cut losers. The bot beats every
  seed on every metric: ₹439k, DD 5.8 % vs 8–13 %, weighted win 63.9 % vs 55–61 %.
- **Edge attribution (EXP-22):** model entries + coin tops ≈ the bot (₹408–439k, wWin 63–64 %); coin entries + model
  tops ≈ the coin. **The edge is the entry signal.** The pattern-top signal is no better than a coin at the same rate.
- So the Stage-A truth (AUC ≈ 0.51 for a signal that carries the whole edge) does not measure entry value. Stage A
  was demoted to a diagnostic (DECISIONS 2026-10-18) and every arm went through Stage B at matched thresholds.
- **Stage B: 0/12 pass** (ledger, "Stage B of the 12 Stage-A arms"). Closest: EXP-10b (OU s-score as a feature),
  Calmar 3/4 half-years, FULL −₹11.6k, DD +1.2 pp, wWin +0.5 pp, but HORIZON −₹371k / wWin −0.9 pp. Worst: the
  outcome-aligned labels (EXP-01/02, −₹255k/−₹329k FULL, wWin −5.5/−7.6 pp) and the no-ML rules. Every arm loses
  2025-H1 and the 2020–26 horizon.
- Stage A's EV@matched ordering largely held up on money, so the demotion did not uncover a wrongly discarded winner.
- Side finding: ISS-15 (training can fit a one-class sample set and crash; latent on HEAD, fixed on `exp/features`).

**Round 1 conclusion stands, now on P&L, drawdown, Calmar and weighted win %:** today's production entry model is not
beaten by any label, feature, rule or market-feature variant tried.
