# Scale-in + loss re-entry block — 2020→2026 horizon and sessions sweep (2026-10-17)

Fixed engine (d9e7bc7). Current 21-name watchlist (17–18 names trade before 2024: STYLAMIND
from 2021-08, ACMESOLAR 2024-11, ATHERENERG 2025-05, KPL 2026-04), ₹6L @ 6.67 %, compounding.
15m history backfilled to 2017-12. Each window is an independent run starting at ₹6L.
Scale-in 50 %/2 tiers/10 % pool; loss block N sessions after a losing full close.

**Survivorship caveat:** the watchlist and per-stock params were chosen on 2023+/2025+ data, so
absolute pre-2024 P&L is optimistic. Comparisons between flag settings on the same names are
the fair part.

## Raw tables

```
window                          baseline |         scale-in Δ |       loss-block Δ |             BOTH Δ
2020-01→2026-10   ₹ 1874.2k DD 42.0% Cal 0.55 |  +144.2k DD 45.8% |  -261.8k DD 34.2% |   +39.1k DD 36.8%
2020              ₹  -46.4k DD 42.0% Cal-0.18 |    -3.2k DD 45.8% |    +3.5k DD 34.2% |   +13.6k DD 36.8%
2021              ₹  155.4k DD  4.2% Cal 6.25 |   +21.5k DD  5.3% |   -26.1k DD  5.7% |    +3.2k DD  6.4%
2022              ₹    4.8k DD  6.9% Cal 0.12 |   +15.5k DD  7.9% |    +7.1k DD  6.7% |   +26.3k DD  6.6%
2023              ₹  157.7k DD  2.7% Cal 9.87 |   +24.3k DD  2.7% |    -8.7k DD  2.3% |   +11.5k DD  2.4%
2024              ₹  172.5k DD  5.5% Cal  5.2 |    -0.6k DD  7.5% |   -36.5k DD  4.3% |   -29.2k DD  5.5%
2025              ₹  118.9k DD  5.9% Cal 3.39 |   +16.9k DD  6.7% |   -22.8k DD  5.0% |    +0.5k DD  5.7%
2026 YTD          ₹  277.8k DD  3.9% Cal15.95 |   +10.9k DD  4.2% |    -4.0k DD  3.4% |   +18.3k DD  3.6%
2020–21           ₹  125.0k DD 42.0% Cal 0.24 |   +20.0k DD 45.8% |   -15.8k DD 34.2% |   +25.1k DD 36.8%
2022–23           ₹  164.7k DD  6.9% Cal 1.88 |   +43.7k DD  7.9% |    -7.3k DD  6.7% |   +48.9k DD  6.6%
2024–25           ₹  301.9k DD 15.0% Cal 1.51 |    +0.2k DD 18.5% |   -56.7k DD 11.3% |   -23.6k DD 13.2%
COVID Feb–Jun 20  ₹ -157.2k DD 40.4% Cal-1.29 |   -14.9k DD 44.5% |   +33.9k DD 33.1% |   +19.1k DD 36.0%
Bear H1-22        ₹  -16.1k DD  6.9% Cal-0.79 |    -2.5k DD  7.9% |    -1.0k DD  6.7% |    +1.5k DD  7.6%
Corr Oct24–Mar25  ₹  -31.3k DD 10.4% Cal-0.98 |    -9.3k DD 13.1% |    +9.9k DD  9.0% |    -1.5k DD  9.9%
  si: beats baseline P&L in 5/7 calendar years; DD ≤ baseline in 1/7
  lb: beats baseline P&L in 2/7 calendar years; DD ≤ baseline in 6/7
  silb: beats baseline P&L in 6/7 calendar years; DD ≤ baseline in 6/7

SESSIONS SWEEP (scale-in ON) — P&L Δ vs baseline / DD%
window                               1                   2                   3                   5                  10
2020-01→2026-10       +68.9k  44.8%     +108.7k  36.2%      +39.1k  36.8%       +9.7k  30.1%       -1.9k  27.0%  
2020                   -1.1k  44.8%      +74.2k  36.2%      +13.6k  36.8%      +87.5k  30.1%     +149.2k  20.6%  
2021                   +4.2k   5.3%      -14.5k   5.8%       +3.2k   6.4%      -36.7k   5.7%      -41.7k   6.0%  
2022                  +27.6k   7.4%      +17.8k   6.7%      +26.3k   6.6%       +7.2k   7.4%      +95.0k   4.1%  
2023                  +13.0k   4.5%       +2.1k   3.4%      +11.5k   2.4%       -8.0k   4.4%       +5.3k   2.5%  
2024                   -9.6k   7.8%      -23.8k   5.6%      -29.2k   5.5%       +6.9k   5.8%      -34.8k   5.1%  
2025                   +8.6k   6.8%       +6.0k   6.8%       +0.5k   5.7%       -9.3k   4.7%      -50.3k   6.3%  
2026 YTD              +14.1k   4.3%      +29.5k   4.3%      +18.3k   3.6%       +5.2k   3.9%      -79.5k   5.6%  
2020–21                -4.5k  44.8%      +80.3k  36.2%      +25.1k  36.8%      +80.6k  30.1%     +146.0k  20.6%  
2022–23               +71.7k   7.4%      +26.3k   6.7%      +48.9k   6.6%       +3.1k   7.4%     +112.0k   4.1%  
2024–25               +13.5k  19.0%      -21.2k  15.8%      -23.6k  13.2%       +2.6k  13.1%      -78.2k  12.9%  
COVID Feb–Jun 20      +15.0k  40.1%      +43.3k  34.3%      +19.1k  36.0%      +93.9k  28.4%     +136.2k  20.3%  
Bear H1-22             +0.2k   7.6%       -2.0k   7.2%       +1.5k   7.6%      -18.3k   7.8%      +47.9k   4.4%  
Corr Oct24–Mar25      -12.7k  13.7%       -8.2k  12.2%       -1.5k   9.9%       -0.6k   9.1%      -12.8k   9.8%  
```

## Reading

- **Baseline 2020→2026: ₹1.87M on ₹6L, max DD 42 % (COVID).** Scale-in alone adds ₹144k but
  deepens the crash DD to 45.8 %. Loss block alone cuts it to 34.2 % but costs ₹262k.
- **Scale-in + loss block, 3 sessions: the most consistent setting.** Beats baseline in 6/7
  calendar years (only 2024 loses, −₹29k), positive even excluding 2020 (+₹30.6k), drawdown ≤
  baseline in 6/7 years, full-period DD 42 → 36.8 %.
- **Longer blocks are crash insurance with a bull-market premium.** 10 sessions: COVID DD 40 →
  20 %, 2020 +₹149k, 2022 bear +₹48k — but 2024/2025/2026 lose ₹35k/₹50k/₹80k; ex-2020 −₹106k.
  5 sessions is the midpoint (full DD 30.1 %, ex-2020 −₹35k, 4/7 years).
- **1 session gives no crash protection** (DD 44.8 %); 2 sessions' +₹109k total is mostly 2020
  (+₹74k), ex-2020 only +₹17k, 5/7 years.
- Weak spot for every setting: 2024 and the Oct-24→Mar-25 correction — the block costs a little
  there whatever its length.

**Recommendation:** ship scale-in + loss block at **3 sessions** (already staged in config).
5–10 sessions only make sense if crash protection is worth ~₹35–105k of normal-year P&L over
six years.
