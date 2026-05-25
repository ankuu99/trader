# Improvement Roadmap

Distilled from the May 2026 calibration exercise. Four sections:
1. **Technical (code/strategy)** — improvements to the existing framework
2. **Qualitative data** — what it is, how to fetch it, how often
3. **AI API integration** — how an LLM layer fits into the system
4. **UI + operational resilience** — what the dashboard must surface; what survives a daily restart

---

## Part 1: Technical Improvements

Ranked by estimated impact. All are implementable within the existing architecture.

---

### P1-A: Market Regime Filter (Highest Impact)

**Problem**: The strategy enters long positions regardless of whether the broad market is trending up or down. In the 2026 correction and 2024 election chop, entries that look like local minima keep forming — but the broader trend is down, so every local low is followed by a new lower low.

**Root cause already solved in data layer**: `_nifty_close` is already injected into every candle dict by the backtest engine and live runner. The strategy just doesn't use it.

**Proposed implementation** in `trader/strategies/lr_extrema.py`:

```python
# In _compute_features or on_candle, before emitting an ENTRY signal:
nifty_closes = [c["_nifty_close"] for c in recent_candles if c.get("_nifty_close")]
if len(nifty_closes) >= 20:
    nifty_slope = (nifty_closes[-1] - nifty_closes[-20]) / nifty_closes[-20]
    if nifty_slope < regime_slope_threshold:   # e.g. -0.03 = NIFTY down >3% over 20 bars
        # suppress entry signal
        return None
```

Add `regime_slope_threshold: -0.03` to `config.yaml` under `lr_extrema`.

**Expected effect**: Would have suppressed most Jan 2026 and Mar 2026 entries that hit SL. In 2024, would have gated election-month (Apr-May) entries. Minimal cost to 2025 since NIFTY was trending up most of the year.

**Complexity**: Low. ~25 lines. No new dependencies.

---

### P1-B: Volatility-Adjusted Position Sizing

**Problem**: A fixed 3% SL (`default_sl_pct`) is too tight for high-ATR small-caps (CUPID, GOKEX, ATHERENERG with 3-5% daily range) and unnecessarily large for low-ATR large-caps (ICICIBANK, LUPIN with 0.8-1.2% daily range). The result: small-caps get stopped out on normal intraday noise, large-caps sit in losers far too long before hitting the 10% SL.

**Proposed implementation**:

In `trader/strategies/lr_extrema.py`, compute ATR over the last 14 bars and pass it as `stop_loss_hint` in the ENTRY signal:

```python
# Compute ATR-14
highs  = [c["high"]  for c in last_14]
lows   = [c["low"]   for c in last_14]
closes = [c["close"] for c in last_14]
tr = [max(h - l, abs(h - cp), abs(l - cp))
      for h, l, cp in zip(highs[1:], lows[1:], closes[:-1])]
atr = sum(tr) / len(tr)

sl_price = entry_price - (atr_sl_multiple * atr)   # e.g. atr_sl_multiple=2.5
```

Add `atr_sl_multiple: 2.5` to config. The risk manager already accepts `signal.stop_loss_hint`, so no changes needed there.

**Expected effect**:
- CUPID (ATR ~₹3, price ~₹85): SL at ₹77.5 instead of ₹76.5. Slightly wider, avoids noise-stops.
- ICICIBANK (ATR ~₹14, price ~₹1,350): SL at ₹1,315 (2.6% away) — tighter than 10%, limits the -10.2% losses we kept seeing.

**Complexity**: Medium. ~40 lines in the strategy, zero changes elsewhere.

---

### P1-C: Dynamic Profit Target Per Stock

**Problem**: `profit_pct=7` is one-size-fits-all. In 2026, BHARTIARTL and LUPIN repeatedly sat in positions for 400 bars (STRATEGY exit) because they never moved 7%. Their 20-bar ATR implies a realistic swing of 3-5%. The 7% bar is simply too high for them.

**Proposed implementation**:

```python
# When emitting entry signal, compute expected_swing from ATR
expected_swing_pct = (atr_20 * sqrt(hold_bars)) / entry_price * 100
dynamic_profit_pct = max(params["profit_pct_min"], min(params["profit_pct_max"],
                         expected_swing_pct * 0.7))
```

Add to config:
```yaml
profit_pct_min: 4.0
profit_pct_max: 10.0
```

Pass `dynamic_profit_pct` as a per-trade override in the signal, and store it alongside the position in the strategy's open-position state.

**Expected effect**: Low-volatility large-caps get a 4-5% TRAILING trigger instead of 7%. This converts the STRATEGY timeout exits into small-positive TRAILING exits, improving the equity curve without changing the core logic.

**Complexity**: Medium-high. Requires per-position state storage for the dynamic threshold. ~60 lines.

---

### P1-D: Volume Divergence Exit Signal

**Problem**: The PATTERN_TOP exit only fires when the model assigns high P(local-max). This is backward-looking by design. Volume divergence (price at new high, volume declining) is a leading indicator that the current run is likely exhausting.

**Proposed implementation** in `on_candle` after a position is open:

```python
# Check for volume divergence once profit_pct is exceeded
if price > peak_price * 0.99:   # near the peak
    vol_ma = mean(c["volume"] for c in last_20)
    if price > max(c["close"] for c in last_5):   # new price high
        if candle["volume"] < vol_ma * volume_divergence_threshold:   # e.g. 0.75
            emit EXIT signal with reason="VOL_DIVERGENCE"
```

Add `volume_divergence_threshold: 0.75` to config (exit if new price high on < 75% of average volume).

**Complexity**: Low. ~20 lines. New exit reason type.

---

### P1-E: Watchlist Stratification

**Problem**: The current watchlist mixes high-alpha small-caps (CUPID, GOKEX, ATHERENERG, DCXINDIA, GUJALKALI) with large-caps that contribute capital deployment without alpha (BHARTIARTL, LUPIN, TATAPOWER). The large-caps fill position slots and block better opportunities.

**Proposed approach**:

Add a `tier` field to watchlist config:
```yaml
watchlist:
  - symbol: NSE:CUPID
    tier: alpha          # high-conviction swing candidates
  - symbol: NSE:ICICIBANK
    tier: anchor         # deployed only when alpha slots < 3
```

In the strategy/risk layer: prefer `tier: alpha` slots. Only open `tier: anchor` positions if fewer than N alpha positions are available.

This doesn't require param tuning — it's a structural change to how capital is allocated across the portfolio.

**Complexity**: Medium. Config schema change, risk manager update (~50 lines).

---

### P2-A: India VIX Gate

**Problem**: High VIX environments (VIX > 18-20) signal elevated uncertainty — new entries during high-VIX periods consistently underperform because the model's training on "normal" volatility candles doesn't generalize to panic-regime candles. `_vix_close` is already fetched; it's just not used.

**Proposed implementation**:

```python
vix = candle.get("_vix_close")
if vix and vix > params.get("vix_entry_block", 20):
    return None   # block new entries during elevated fear
```

**Complexity**: Trivial. 5 lines.

---

### P2-B: Intraday vs Overnight Risk Differentiation

**Problem**: MIS (intraday) and CNC (delivery) positions are sized identically. In practice, an overnight gap risk on a CNC position is materially higher than intraday risk on MIS. The current SL of 10% is intended for CNC but is applied equally.

**Proposed implementation**: When the signal is CNC, apply an overnight gap buffer — increase SL by 20% of ATR to account for gap risk. When MIS, use a tighter SL since the position closes same day.

**Complexity**: Low. ~15 lines in risk manager.

---

## Part 2: Qualitative Data in the System

### What "Qualitative Data" Means Here

The strategy is entirely quantitative — price, volume, model probabilities. But real market moves are often driven by information that doesn't appear in candlestick data until after the fact:

| Category | Examples | Impact on trades |
|---|---|---|
| **Company events** | Earnings results, QoQ revenue, promoter buying/selling, block deals | Can invalidate a technically valid entry overnight |
| **Macro events** | RBI rate decisions, Union Budget, US Fed meetings, election results | Creates regime shifts that persist for days or weeks |
| **Regulatory** | SEBI notifications, ASM/GSM listing, NCLT orders, pledged share alerts | Immediate risk — should block entries entirely |
| **Sector news** | PLI scheme announcements, import duties, sectoral tailwinds/headwinds | Changes the expected holding period and direction |
| **FII/DII flows** | Daily net buy/sell from NSE; institutional positioning | Confirms or contradicts individual stock signals |
| **Global sentiment** | US market overnight, SGX Nifty futures, crude oil moves | Sets the opening gap context each morning |

---

### How to Fetch Each Type

#### Structured / API-accessible (reliable, automatable)

| Data | Source | Method | Frequency |
|---|---|---|---|
| FII/DII daily flows | NSE India (nseindia.com) | HTTP scrape or unofficial NSE API (nsetools / nsepython) | Daily, 6:30 PM |
| Economic calendar | RBI website, Investing.com | HTTP fetch + parse | Weekly, Sunday |
| SEBI ASM/GSM list | SEBI PDF or BSEIndia | PDF scrape, compare vs watchlist | Daily, before market open |
| Promoter shareholding | NSE bulk/block deals CSV | Download from NSE bulk deal archive | Daily |
| Earnings calendar | NSE corporate actions | NSE corporate action API | Weekly |
| SGX Nifty pre-market | Broker data or NSEpy | API call | Daily, 8:30 AM |

#### Unstructured / Requires AI summarization

| Data | Source | What to Extract |
|---|---|---|
| News articles | NewsAPI, Google News RSS, MoneyControl RSS | Sentiment per stock: positive / negative / neutral, event type |
| RBI/SEBI press releases | rbi.org.in, sebi.gov.in RSS | Policy change signal, sector impact |
| Earnings call transcripts | NSE filings, screener.in | Management tone, guidance revision |
| Analyst reports | Broker PDFs | Rating changes, target price changes |
| Twitter/Reddit | X API (expensive), StockTwits | Retail sentiment, unusual activity |

---

### Recommended Injection Frequency

The key principle: **don't inject noise, inject signals**. Qualitative data should update only when the underlying reality changes.

| Data Type | Update Frequency | How Injected |
|---|---|---|
| ASM/GSM blacklist | Daily pre-market (~8:45 AM) | Block instrument entirely in config or risk manager |
| FII/DII net flows | Daily post-market (~6:30 PM) | As a regime bias for next day: `_fii_net_buy_pct` in candle dict |
| Macro calendar | Weekly (Sunday evening) | Flag specific dates as "event days" — reduce position size or block entries |
| Earnings dates | Weekly | Flag T-2 to T+1 around earnings as no-entry window per instrument |
| News sentiment | Daily pre-market | Per-stock sentiment score (-1 to +1), blocks entry if < threshold |
| Promoter sells | Daily | Immediate block for 10 trading days if promoter sold > 1% stake |

**Practical storage**: A lightweight JSON sidecar file (`data/qualitative_context.json`) updated by a separate daily script. The strategy reads it at startup and checks it on each entry signal:

```json
{
  "NSE:CUPID": {
    "sentiment_score": 0.3,
    "event_window": null,
    "asm_listed": false,
    "promoter_alert": false,
    "last_updated": "2026-05-25"
  },
  "macro": {
    "regime": "risk_off",
    "next_rbi_date": "2026-06-06",
    "fii_5d_net_flow_cr": -1240
  }
}
```

The strategy checks this on ENTRY signals:

```python
ctx = qualitative_context.get(instrument, {})
if ctx.get("asm_listed"):
    return None   # hard block
if ctx.get("sentiment_score", 0) < -0.5:
    return None   # block on strongly negative news
if ctx.get("event_window"):   # earnings in T-2 to T+1
    return None
```

**Update cadence**: A cron job or scheduled script runs at 8:45 AM (post-SGX Nifty, pre-market open) and at 6:00 PM (post-close). It fetches, processes, and writes the JSON. The live trading loop reads this file fresh each morning on startup.

---

## Part 3: AI API Integration

### The Core Problem an LLM Solves Here

The gap between structured quant data (OHLCV, model probabilities) and unstructured qualitative data (news, filings, analyst tone) is exactly what LLMs are good at bridging. Specifically:

1. **Summarize** a news article or SEBI circular into a structured signal
2. **Assess** whether a macro event (e.g. "RBI cuts rate by 50bps") is net positive or negative for a specific sector
3. **Flag** anomalies: promoter pledging, related-party transactions, sudden volume spikes with no news explanation
4. **Generate** a daily market context summary the trader can review in 60 seconds before open

---

### Proposed Architecture

```
                      ┌─────────────────────────────────────────┐
                      │         Daily Intelligence Pipeline      │
                      │  (runs at 8:00 AM, writes JSON sidecar)  │
                      └─────────────────────────────────────────┘
                                          │
           ┌──────────────────────────────┼──────────────────────────────┐
           │                              │                              │
    ┌──────▼──────┐              ┌────────▼──────┐              ┌───────▼──────┐
    │ News Fetcher│              │ Macro Calendar│              │  FII/DII     │
    │ (RSS/API)   │              │  + RBI/SEBI   │              │  Flow Fetcher│
    └──────┬──────┘              └────────┬──────┘              └───────┬──────┘
           │                              │                              │
           └──────────────────────────────▼──────────────────────────────┘
                                          │
                               ┌──────────▼──────────┐
                               │   LLM Summarizer    │
                               │   (Claude API)      │
                               │                     │
                               │  Input: raw text    │
                               │  Output: JSON signal│
                               └──────────┬──────────┘
                                          │
                               ┌──────────▼──────────┐
                               │  qualitative_context │
                               │       .json          │
                               └──────────┬──────────┘
                                          │
                               ┌──────────▼──────────┐
                               │   lr_extrema.py      │
                               │  (reads on ENTRY     │
                               │   signal check)      │
                               └─────────────────────┘
```

---

### What the LLM Does at Each Step

#### Step 1 — Per-stock news digest (daily)

Fetch last 24h headlines for each watchlist stock from NewsAPI or Google News RSS. Send to Claude:

```
System: You are a financial news analyst for Indian equities. Respond only in valid JSON.

User: Here are today's news headlines for NSE:CUPID (Cupid Ltd, NSE-listed condom manufacturer):
  1. "Cupid Q4 results: Net profit jumps 35% YoY on strong export demand"
  2. "Cupid to expand capacity by 40% — board approves ₹120 Cr capex"

Classify the sentiment and any event flags:
{
  "sentiment_score": <float -1.0 to 1.0>,
  "event_type": <"earnings_beat"|"earnings_miss"|"capex"|"promoter_action"|"regulatory"|"none">,
  "entry_block": <true|false>,
  "entry_block_reason": <string or null>,
  "confidence": <"high"|"medium"|"low">
}
```

Claude returns structured JSON that goes directly into `qualitative_context.json`.

#### Step 2 — Macro regime assessment (daily pre-market)

Aggregate macro signals (FII flow, global market overnight, VIX) into a single LLM call:

```
System: You are a macro analyst for Indian equities trading. Respond only in valid JSON.

User: Today's context:
  - SGX Nifty pre-market: -0.8%
  - US markets yesterday: S&P500 -1.2%, Nasdaq -1.8%
  - India VIX: 18.4 (yesterday: 16.2)
  - FII last 5 days net: -₹3,400 Cr
  - RBI policy meeting: 12 days away
  - Crude oil: +2.1% (WTI $83)

Assess the market regime for Indian equities intraday:
{
  "regime": <"risk_on"|"neutral"|"risk_off">,
  "entry_bias": <"allow"|"reduce_size"|"block">,
  "key_risk": <string, 1 sentence>,
  "confidence": <"high"|"medium"|"low">
}
```

If `entry_bias = "block"`, the strategy suppresses all new entries for the session.

#### Step 3 — Pre-earnings event window detection (weekly)

Once per week, fetch the corporate actions calendar from NSE for the upcoming 10 trading days. LLM maps company names to watchlist symbols and identifies "event windows":

```python
# Output used to populate event_window field per instrument:
"NSE:DCXINDIA": {
    "event_window": {"from": "2026-05-28", "to": "2026-06-03", "reason": "Q4 results expected"}
}
```

No new entries within the event window. Existing positions are held (not force-exited).

#### Step 4 — Telegram daily briefing

After the morning LLM run, compose a 5-bullet summary and send via the existing `telegram.notify()` infrastructure:

```
🧠 Morning Intelligence [2026-05-26]
Regime: RISK_OFF (VIX 18.4, FII -₹680Cr)
Blocked entries today: ICICIBANK (negative news), ABFRL (earnings T-1)
Watchlist sentiment: GOKEX ↑, CUPID neutral, ATHERENERG ↓
Key risk: Fed minutes tonight may move EM flows
Suggested: Allow entries only if NIFTY opens flat or positive
```

---

### Backtesting Design — Neutral Pass-Through

The qualitative gate cannot be replayed historically (no archived sentiment scores, no point-in-time ASM status). The chosen approach is **neutral pass-through**: in backtest mode, `QualitativeGate.should_block_entry()` always returns `False`. Backtests measure pure quantitative alpha; the qualitative layer is live-only.

This means:
- Backtest results represent the **upper bound** of what live performance can be (no qualitative blocks).
- Any improvement the qualitative gate delivers in live is additive and not yet captured in backtests.
- The regime filter (NIFTY slope, VIX) is quantitative and **is** backtested — only the AI sentiment/event layer is neutral.

**Implementation — `QualitativeGate` protocol:**

```python
# trader/data/qualitative.py

class QualitativeGate:
    """Abstract interface. Strategy calls this; never instantiates concretely."""
    def should_block_entry(self, instrument: str) -> tuple[bool, str]:
        """Returns (blocked: bool, reason: str)."""
        raise NotImplementedError

class LiveGate(QualitativeGate):
    """Reads intelligence_log.json written by the daily pipeline."""
    def __init__(self, log_path):
        self._data = json.load(open(log_path)) if Path(log_path).exists() else {}

    def should_block_entry(self, instrument):
        inst = self._data.get("instruments", {}).get(instrument, {})
        if inst.get("block"):
            return True, inst.get("block_reason", "qualitative block")
        macro = self._data.get("macro", {})
        if macro.get("entry_bias") == "block":
            return True, f"macro: {macro.get('key_risk', 'risk_off')}"
        return False, ""

class NeutralGate(QualitativeGate):
    """Backtest implementation — never blocks. Zero cost, zero side effects."""
    def should_block_entry(self, instrument):
        return False, ""
```

In `run_backtest()` (engine), pass `gate=NeutralGate()` to the strategy. In `main.py` (live), pass `gate=LiveGate(intelligence_log_path)`. The strategy calls `self._qual_gate.should_block_entry(instrument)` — same call site either way.

---

### Integration Touchpoints in Existing Code

| Existing file | Change required |
|---|---|
| `scripts/daily_intelligence.py` | **New file** — the daily pipeline script |
| `trader/data/qualitative.py` | **New file** — `QualitativeGate` protocol + `LiveGate` + `NeutralGate` |
| `trader/strategies/lr_extrema.py` | Accept `qual_gate` at init; call `qual_gate.should_block_entry()` before ENTRY signal |
| `trader/backtest/engine.py` | Pass `NeutralGate()` to strategy constructor |
| `main.py` | Pass `LiveGate(path)` to strategy constructor; call `daily_intelligence.run()` at startup |
| `trader/core/config.py` | Add `qualitative.enabled`, `qualitative.sentiment_threshold`, `qualitative.block_on_risk_off` |
| `config/.env` | Add `ANTHROPIC_API_KEY` |

---

### API Cost Estimate

| Call type | Tokens (approx) | Daily calls | Daily cost (Claude Haiku) |
|---|---|---|---|
| Per-stock news digest | ~500 in, ~150 out | 22 stocks | ~$0.003 |
| Macro regime assessment | ~300 in, ~100 out | 1 | ~$0.0003 |
| Weekly earnings calendar | ~400 in, ~200 out | 1/week | ~$0.0004/day |
| **Total** | | | **~$0.004/day (~₹0.33)** |

Effectively zero cost. Even with Claude Sonnet for higher-quality analysis it's under $0.05/day.

---

### What to Use — Model Recommendation

| Task | Recommended model | Reason |
|---|---|---|
| Per-stock news sentiment | `claude-haiku-4-5` | Simple classification, high volume, cost matters |
| Macro regime assessment | `claude-sonnet-4-6` | Nuanced multi-factor reasoning, once daily |
| Earnings event detection | `claude-haiku-4-5` | Structured extraction, low complexity |
| Telegram briefing composition | `claude-haiku-4-5` | Text generation, style consistency |

Use Anthropic's official Python SDK (`anthropic` package) for structured JSON output via the `tool_use` or `response_format` feature to guarantee parseable responses.

---

## Summary: Prioritized Implementation Order

| Priority | Item | Effort | Expected Impact |
|---|---|---|---|
| 🔴 P0 | **[SAFETY]** Fallback P&L seed from orders table (Part 4) | Low (20 lines) | Safety — daily loss limit must work after mid-day restart |
| 🔴 P0 | NIFTY regime filter (P1-A) | Low (25 lines) | High — directly fixes the 2026 correction problem |
| 🔴 P0 | India VIX gate (P2-A) | Trivial (5 lines) | Medium — free signal, already fetched |
| 🟠 P1 | Startup + warmup Telegram notifications (Part 4) | Low (15 lines) | High ops — daily heartbeat without SSH |
| 🟠 P1 | BotState lifecycle + regime fields + regime/intelligence UI panels (Part 4) | Medium (3 files) | High ops — operator visibility into gates and AI context |
| 🟠 P1 | `sl_price` in DB + SL proximity UI column (Part 4) | Low (20 lines) | High ops — positions approaching SL are invisible today |
| 🟠 P1 | Qualitative JSON sidecar + ASM/GSM check (Part 2/3) | Medium (2 files) | High — prevents catastrophic entries on regulatory news |
| 🟠 P1 | ATR-based stop loss (P1-B) | Medium (40 lines) | High — reduces false SL triggers and runaway losses |
| 🟡 P2 | AI daily intelligence pipeline (Part 3) | Medium (1 new script) | High qualitative uplift, ~$0.004/day |
| 🟡 P2 | `intelligence_log.json` + intelligence UI panel (Part 4) | Low (tied to above) | Ops — shows morning AI run status on dashboard |
| 🟡 P2 | Today's closed trades panel + daily counter strip (Part 4) | Low (20 lines) | Medium ops — at-a-glance daily activity |
| 🟡 P2 | Dynamic profit target per stock (P1-C) | Medium-high (60 lines) | Medium — fixes large-cap STRATEGY exit drag |
| 🟢 P3 | Watchlist stratification (P1-E) | Medium (config + risk manager) | Medium — better capital allocation |
| 🟢 P3 | Volume divergence exit (P1-D) | Low (20 lines) | Low-medium — complementary signal |
| 🟢 P3 | Overnight gap buffer (P2-B) | Low (15 lines) | Low — marginal risk reduction |

The P0 items (regime filter + VIX gate) can be shipped in an afternoon and would have materially improved every underperforming window we tested. Everything else builds on that foundation.

---

## Part 4: UI + Operational Resilience (Daily Restart Survival)

### The Problem

The system runs on a remote server and **restarts every day at 08:15 IST** to refresh the Kite session token. Everything in `BotState` and `RiskManager` in-memory objects resets to zero on each restart. The SQLite database persists. Anything not in the DB is invisible after a restart.

The current UI (`trader/ui/`) already reads open positions, orders, and signals from the DB. But it has no visibility into:
- What the regime filter / VIX gate are currently doing
- Whether the morning intelligence pipeline ran and succeeded
- Which instruments are blocked by qualitative context today
- The startup lifecycle (STARTING → WARMING_UP → READY → TRADING)
- An operator-facing startup notification confirming the bot came up cleanly

Every new feature added (regime filter, qualitative data, AI pipeline) creates new state that needs to survive restarts and be visible in the UI.

---

### What Survives a Restart (Persistence Map)

| Data | Storage | Survives restart? | Notes |
|---|---|---|---|
| Open positions | SQLite `open_positions` | ✅ | Re-seeded into RiskManager on startup |
| Order history | SQLite `orders` | ✅ | Read-only after restart |
| Signal log | SQLite `signals` | ✅ | Read-only after restart |
| Candle cache | SQLite `candles` | ✅ | Warmup reads from here |
| Cumulative P&L | SQLite (seeded via `seed_cumulative_pnl`) | ✅ | Already handled |
| **Qualitative context** | `data/qualitative_context.json` | ✅ | File on disk; written by daily pipeline |
| **Intelligence run log** | `data/intelligence_log.json` | ✅ | New file — tracks last run status |
| `BotState.started_at` | In-memory | ❌ resets | Intentional |
| `BotState.warmup_done` | In-memory | ❌ resets | Recomputed during warmup — correct |
| Regime filter state | In-memory | ❌ resets | Recomputed per candle after warmup — correct |
| `RiskManager._realised_pnl` | In-memory | ❌ resets | **Gap**: daily loss limit blind after mid-day restart if broker P&L seed fails |

**Critical gap — P0 safety fix**: If `seed_realised_pnl()` from broker returns 0 on a mid-day restart, the daily loss limit check is blind. Add a fallback in `main.py` that computes today's realised P&L from the `orders` table directly (sum of filled SELL order P&L where `date(placed_at) = today`) and seeds it if the broker returns 0.

---

### New Fields to Add to `BotState` (`trader/ui/state.py`)

```python
@dataclass
class BotState:
    # existing fields unchanged ...

    # --- new fields ---
    lifecycle: str = "STARTING"
    # Values: STARTING | WARMING_UP | READY | TRADING | HALTED | ERROR
    # main.py sets these; dashboard reads them.

    regime_status: dict = field(default_factory=dict)
    # {
    #   "nifty_slope_20": float,     # current 20-bar NIFTY return (%)
    #   "nifty_blocking": bool,      # True if regime filter suppressing entries
    #   "vix_current": float,
    #   "vix_blocking": bool,
    #   "last_updated_at": datetime
    # }

    intelligence_status: dict = field(default_factory=dict)
    # {
    #   "last_run_at": str,          # ISO datetime of last intelligence run
    #   "last_run_ok": bool,
    #   "macro_regime": str,         # "risk_on" | "neutral" | "risk_off"
    #   "macro_key_risk": str,
    #   "blocked_instruments": list,
    #   "block_reasons": dict        # {symbol: reason_str}
    # }

    today_summary: dict = field(default_factory=dict)
    # {
    #   "entries_today": int,
    #   "exits_today": int,
    #   "entries_blocked_regime": int,
    #   "entries_blocked_qualitative": int,
    # }
```

The strategy writes to `bot_state.regime_status` each time the regime check runs. `main.py` reads `intelligence_log.json` at startup and populates `bot_state.intelligence_status`.

---

### New Dashboard Panels (`trader/ui/template.py`)

#### Panel 1 — Lifecycle Banner (replaces the header badges)

```
[ LIVE ] [ MARKET OPEN ] [ WARMING UP — 14/22 instruments ]  09:12 IST  uptime 0h 3m
                         ████████████░░░░░░░░  63%
```

After warmup: `[ READY — 22/22 trained ]` in green. On HALTED: red banner across full width.

---

#### Panel 2 — Regime Gates Card (2-col grid, left)

```
┌──────────────────────────────────┐
│  REGIME GATES                    │
│                                  │
│  NIFTY 20-bar:  -1.2%  BLOCKING  │
│  India VIX:     19.4   BLOCKING  │
│                                  │
│  Blocked today by gates: 7       │
└──────────────────────────────────┘
```

`BLOCKING` badge in red; `CLEAR` in green. Counter sourced from `bot_state.today_summary["entries_blocked_regime"]`.

---

#### Panel 3 — Morning Intelligence Card (2-col grid, right; only if `qualitative.enabled`)

```
┌──────────────────────────────────┐
│  MORNING INTELLIGENCE  ✓ 08:47   │
│                                  │
│  Macro:   RISK_OFF               │
│  Risk:    Fed minutes at 23:00   │
│                                  │
│  Blocked (3): ICICIBANK ABFRL    │
│               LUPIN              │
└──────────────────────────────────┘
```

If run failed:

```
│  MORNING INTELLIGENCE  ✗ FAILED  │
│  Using stale context: 2026-05-24 │
```

Sourced from `bot_state.intelligence_status` (populated from `intelligence_log.json` at startup).

---

#### Panel 4 — SL Proximity in Open Positions Table

Extend the existing positions table with two columns: `SL Price` and `SL dist%`. Color the row orange if within 2% of SL, red if within 1%.

| Symbol | Qty | Entry | Current | Unreal. P&L | SL Price | SL dist | Status |
|---|---|---|---|---|---|---|---|
| CUPID | 64 | ₹84.20 | ₹90.50 (+7.4%) | +₹401 | ₹75.78 | 16.3% | TRAILING |
| GOKEX | 6 | ₹724.30 | ₹698.00 (-3.6%) | -₹158 | ₹651.87 | **6.7%** | OPEN (orange) |

SL is stored (or derived as `entry × (1 - stop_pct/100)`) at fill time. Needs `sl_price` column added to `open_positions` DB table.

---

#### Panel 5 — Today's Closed Trades

A compact table built from pairs of BUY+SELL orders where `date(placed_at) = today`:

```
┌──────────────────────────────────────────────────────┐
│  TODAY'S CLOSED TRADES                               │
│  Symbol   Entry    Exit    Qty  P&L     Reason       │
│  CUPID    ₹84.20  ₹90.50   53  +₹329  TRAILING      │
│  ABFRL    ₹63.61  ₹57.25   70  -₹451  SL            │
└──────────────────────────────────────────────────────┘
```

Sourced from `orders` table with a join on entry/exit pairs.

---

#### Panel 6 — Daily Counter Strip (one line, full width, below header)

```
Today:  5 entries  ·  3 exits  ·  7 regime-blocked  ·  2 qual-blocked  ·  Realised P&L  +₹412
```

Sourced from `bot_state.today_summary` + `risk._realised_pnl`.

---

### Telegram Startup Notifications

Add to `trader/notifications/telegram.py`:

```python
def notify_startup(capital: float, open_positions: int, env: str, intelligence_ok: bool):
    """Sent immediately when main.py starts — confirms clean restart."""
    intel = "intelligence loaded" if intelligence_ok else "INTELLIGENCE UNAVAILABLE"
    msg = (
        f"Bot started [{env.upper()}]\n"
        f"Capital: {capital:,.0f}  Open carried over: {open_positions}\n"
        f"{intel}"
    )
    _send(msg)

def notify_warmup_complete(trained: int, total: int, env: str):
    """Sent after all instruments are trained — confirms bot is ready to trade."""
    _send(f"Warmup complete [{env.upper()}] — {trained}/{total} instruments ready.")
```

These two messages give the operator a reliable daily heartbeat without needing SSH or dashboard access.

---

### `data/intelligence_log.json` Schema

Written by `scripts/daily_intelligence.py`, read by `main.py` at startup. Fails gracefully if absent (no qualitative blocking, UI shows "not configured").

```json
{
  "run_at": "2026-05-26T08:47:12",
  "run_ok": true,
  "macro": {
    "regime": "risk_off",
    "entry_bias": "reduce_size",
    "key_risk": "Fed minutes at 23:00 may trigger EM outflows",
    "confidence": "medium"
  },
  "fii_5d_net_cr": -1240,
  "vix_snapshot": 18.4,
  "nifty_premarket_pct": -0.8,
  "instruments": {
    "NSE:CUPID":     {"sentiment_score": 0.4, "asm_listed": false, "event_window": null, "block": false},
    "NSE:ICICIBANK": {"sentiment_score": -0.6, "asm_listed": false, "event_window": null, "block": true, "block_reason": "negative news: margin pressure Q4"},
    "NSE:ABFRL":     {"sentiment_score": 0.1, "asm_listed": false, "event_window": {"from": "2026-05-27", "to": "2026-05-30", "reason": "Q4 results"}, "block": true, "block_reason": "event window: Q4 results"}
  }
}
```

If file age > 24h: UI shows a yellow staleness warning but continues using the last known data for sentiment. Hard flags (`asm_listed: true`) remain enforced regardless of file age.

---

### Implementation Checklist — Restart Resilience

| Item | Files | Survives restart? | Priority |
|---|---|---|---|
| Fallback P&L seed from orders table | `main.py`, `risk/manager.py` | ✅ (reads DB) | **P0 safety** |
| `intelligence_log.json` written by pipeline | `scripts/daily_intelligence.py` | ✅ | P1 |
| Read `intelligence_log.json` at startup | `main.py` | ✅ (file) | P1 |
| `sl_price` column in `open_positions` table | `trader/data/store.py` | ✅ | P1 |
| Add `lifecycle`, `regime_status`, etc. to BotState | `state.py` | ❌ resets (correct) | P1 |
| Strategy writes to `bot_state.regime_status` | `lr_extrema.py` | ❌ resets | P1 |
| Startup + warmup Telegram notifications | `main.py`, `telegram.py` | n/a | P1 |
| Regime Gates panel | `template.py` | reads in-memory | P1 |
| Intelligence panel | `template.py` | reads in-memory from startup-loaded file | P1 |
| Lifecycle banner | `template.py` | reads in-memory | P2 |
| SL proximity in positions table | `template.py` | reads DB | P2 |
| Today's closed trades panel | `template.py` | reads DB | P2 |
| Daily counter strip | `template.py` | reads in-memory + DB | P2 |
