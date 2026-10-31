# Trendlyne Integration — Complete Reference

This document describes exactly how the FVM system fetches, stores, and uses financial data from
Trendlyne. It is self-contained and portable — everything needed to replicate this integration in
another project is here.

---

## What Trendlyne provides

Trendlyne's **Excel Connect** feature (paid plan) exposes a REST API (`fincsv/v1`) that returns
pre-processed, multi-year financials in CSV form. It is NOT a public API — it is the API that
backs the Excel Add-in / Google Sheets Apps Script. We call it directly with the same auth that
the Apps Script uses.

The data covers:
- **Quarterly financials** — P&L, margins, EPS, EBITDA, revenue growth (60 fields, ~13 quarters deep)
- **Annual financials** — full P&L + balance sheet + cash flow + ratios + long-term CAGRs (189 fields, ~10 years deep)
- **Master stock list** — all NSE/BSE symbols with their internal `stock_hash` identifiers

The Trendlyne quarterly window is **hard-capped at ~13 quarters** back from the most recent
filing date. As of 2023, this means quarterly data starts around 2023-03 at the earliest. Annual
data reaches back to ~2013. This is a platform constraint — confirmed across both the Excel
Connect API and the website endpoint. Do not probe for older quarters; the cap is fixed.

---

## API endpoints

Base URL: `https://trendlyne.com/fundamentals/fincsv/v1`

| Path | Auth required | Returns | Notes |
|------|---------------|---------|-------|
| `GET /get-expiry/` | Token only | JSON `{expires_on, is_expired}` | Token validity check |
| `GET /all_stocks/` | Token only | CSV master list | ~5000 rows; `NSEcode → stock_hash` |
| `GET /quarter/?stock_hash=<h>` | Token + Cookie | CSV quarterly financials | 60 fields × ~13 quarters |
| `GET /annual/?stock_hash=<h>` | Token + Cookie | CSV annual financials | 189 fields × ~10 years |

The `stock_hash` is a Trendlyne-internal Base64-like identifier. It is **not** the ISIN or NSE
code. You must fetch the master list first to build the `nsecode → stock_hash` mapping.

---

## Authentication

Two credentials are required:

### 1. `TRENDLYNE_TOKEN` (stable)
- Obtain from: **Trendlyne → Tools → Excel Connect → "Copy token"** (a long hex/base64 string)
- Sent as HTTP header: `tltoken: Token <your_token>`
- Token-only endpoints (`get-expiry`, `all_stocks`) work with just this
- Relatively stable — changes only if you regenerate it manually

### 2. `TRENDLYNE_COOKIE` (session; requires manual refresh)
- Required for the data endpoints (`quarter`, `annual`)
- Obtain by logging into trendlyne.com in a browser and copying the full `Cookie:` header value
  from any authenticated request (e.g. via browser DevTools → Network tab)
- Sent as HTTP header: `Cookie: <value>`
- Expires when the browser session expires (roughly monthly). Must be refreshed manually.
- Store in `config/.env` as `TRENDLYNE_COOKIE=<value>`

### User-Agent — critical
The data endpoints (`quarter`, `annual`) are WAF-protected and will return 403 for generic Python
`requests` User-Agents. The only confirmed working UA is the **Google Apps Script UrlFetchApp UA**:

```
Mozilla/5.0 (compatible; Google-Apps-Script; beanserver; +https://script.google.com; id: trendlyne-fvm)
```

This was discovered by inspecting the Excel Connect Apps Script source. The token-only endpoints
(`get-expiry`, `all_stocks`) work with any UA, but use the same UA everywhere to avoid surprises.

---

## Rate limits

| Limit | Value |
|-------|-------|
| Financials fetches per day | ~50 |
| Financials fetches per month | ~500 |
| Calls per stock per ingest | 2 (`quarter` + `annual`) |
| Effective daily new-stock capacity | ~25 stocks/day |

`all_stocks` and `get-expiry` do **not** count against this budget. Only `quarter` and `annual`
calls do. The ingest script is resumable — already-ingested stocks are skipped, so you can fill
a universe of 350+ names over ~2 weeks.

---

## Environment setup

In `config/.env`:
```
TRENDLYNE_TOKEN=<your_token_from_excel_connect_page>
TRENDLYNE_COOKIE=<full_cookie_header_from_browser_devtools>
```

Both are loaded via `python-dotenv` (`load_dotenv("config/.env")`).

---

## Code structure

### `trader/fvm/data/trendlyne.py` — the HTTP adapter

**`TrendlyneClient`** — thin HTTP wrapper around the fincsv API.

```python
from trader.fvm.data.trendlyne import TrendlyneClient, TrendlyneError

client = TrendlyneClient()          # reads token/cookie from config/.env
client = TrendlyneClient(token="...", cookie="...")   # explicit

# token-only
expiry = client.expiry()            # -> {expires_on, is_expired}
stocks = client.all_stocks()        # -> list[{isin, nsecode, bsecode, name, stock_hash, currency}]

# cookie-gated
csv_text = client.quarter_csv("abc123==")    # raw CSV string
csv_text = client.annual_csv("abc123==")     # raw CSV string
```

Error types raised:
- `TrendlyneError("429 rate-limited: ...")` — daily/monthly quota reached
- `TrendlyneError("403 on ...: token/cookie invalid or expired")` — stale cookie or bad token
- `TrendlyneError("This endpoint needs TRENDLYNE_COOKIE ...")` — cookie not set

**`parse_financials_csv(text)`** — parses the raw CSV into `[{field, period, value}]` dicts.

CSV structure: rows = financial parameters, columns = time periods (`"Mar 2026"`, `"Dec 2025"`, ...).
Column 0 is the field name. Period headers are normalized to `"YYYY-MM"` format. Values are
cleaned (commas removed, `%` stripped, `-`/`NA`/`N/A` → skip).

```python
from trader.fvm.data.trendlyne import parse_financials_csv

rows = parse_financials_csv(csv_text)
# -> [{"field": "Net Profit Qtr", "period": "2026-03", "value": 1234.5}, ...]
```

**`ingest_master(store, client)`** — fetches `all_stocks` and upserts into `fund_stocks` table. Token-only.

**`ingest_financials(store, nsecode, client, basis="consolidated")`** — fetches `quarter` + `annual`
CSVs for one stock and writes to the `fundamentals` table. Needs cookie. Counts as 2 API calls.

```python
from trader.fvm.data.trendlyne import ingest_master, ingest_financials

ingest_master(store)                # one-time: populate fund_stocks
ingest_financials(store, "RELIANCE")
```

**Point-in-time knowledge_date** — each row written by `ingest_financials` gets:

```
knowledge_date = period_end_date + 45 days
```

e.g. a `"2026-03"` period (March 2026 quarter) becomes `knowledge_date = "2026-05-15"`. This is a
conservative reporting-lag assumption (Indian companies have 45 days to file quarterly results).
The PIT query then returns the value only if `knowledge_date <= asof`, preventing look-ahead bias
in backtests.

---

### `trader/fvm/data/store.py` — the SQLite PIT store

**`FVMStore`** — append-only, vintaged EAV store. Lives in `data/fvm.db` (isolated from the
trading `market.db`).

Key tables:

| Table | Purpose |
|-------|---------|
| `fund_stocks` | `nsecode → stock_hash` master, plus ISIN/BSE/name |
| `fundamentals` | EAV vintaged financials (PK = symbol+statement+basis+period+field+knowledge_date) |
| `shareholding` | Promoter/FII/DII/pledge (source: Screener.in, not Trendlyne) |
| `sector_map` | Symbol → NSE macro industry |
| `index_membership` | PIT index constituent intervals |

**Key methods:**

```python
store = FVMStore("data/fvm.db")

# master
store.upsert_stocks(rows)                         # rows from client.all_stocks()
h = store.get_stock_hash("RELIANCE")              # "abc123==" or None

# write
store.write_fundamentals(rows)                    # rows from ingest_financials

# PIT read — returns {period: value} for all periods knowable as of `asof`
d = store.read_fundamental_asof(
    symbol="RELIANCE",
    statement="quarter",          # "quarter" | "annual"
    basis="consolidated",
    field="Net Profit Qtr",
    asof="2025-06-01"             # YYYY-MM-DD
)
# -> {"2025-03": 19123.0, "2024-12": 18765.0, ...}
```

The PIT query uses a correlated subquery to pick the vintage with `MAX(knowledge_date) <= asof`
per period — i.e. the most recently known value as of the query date, never future data.

---

### `trader/fvm/fields.py` — field name catalog

Central registry mapping semantic factor names to `(statement, field_name)` tuples for
`FVMStore.read_fundamental_asof`. All Trendlyne field-name coupling lives here.

```python
from trader.fvm import fields as F

# Usage: store.read_fundamental_asof(sym, *F.NET_PROFIT_Q, basis, asof)
NET_PROFIT_Q       = ("quarter", "Net Profit Qtr")
TOTAL_REVENUE_Q    = ("quarter", "Total Revenue Qtr")
OPM_Q              = ("quarter", "Operating Profit Margin Qtr %")
REVENUE_GROWTH_Q   = ("quarter", "Revenue Growth Qtr YoY %")
EBITDA_Q           = ("quarter", "EBITDA Qtr")
BASIC_EPS_Q        = ("quarter", "Basic EPS Qtr")

EV_EBITDA_A        = ("annual", "EV Per EBITDA Annual")
EPS_A              = ("annual", "EPS Annual")
NET_PROFIT_A       = ("annual", "Net Profit Annual")
CFO_A              = ("annual", "Cash from Operating Activity Annual")
DE_A               = ("annual", "Total Debt to Total Equity Annual")
INT_COVERAGE_A     = ("annual", "Interest Coverage Ratio Annual")
ROCE_A             = ("annual", "ROCE Annual %")
ROE_A              = ("annual", "ROE Annual %")
TOTAL_REVENUE_A    = ("annual", "Total Revenue Annual")
REVENUE_GROWTH_A   = ("annual", "Revenue Growth Annual YoY %")
# ... (see fields.py for full list)
```

The full field catalog (all 60 quarterly + 189 annual fields) is documented in
`docs/FVM_Trendlyne_Fields.md`.

---

### `scripts/fvm_ingest.py` — the ingestion runner

Rate-budgeted, resumable ingestion script. Run daily to fill the universe incrementally.

```bash
# Standard run (fills up to 40 financials from the universe, mid-cap-first)
python scripts/fvm_ingest.py [--max-financials 40] [--index NIFTY500] [--db data/fvm.db]

# On-demand: fetch specific symbols (e.g. watchlist names outside Nifty500)
python scripts/fvm_ingest.py --symbols CUPID,RADICO
python scripts/fvm_ingest.py --symbols NSE:CUPID,NSE:RADICO
```

**What it does on each run:**

1. **One-time scaffolding** (idempotent, guarded):
   - `ingest_master` — populates `fund_stocks` if empty (token-only, unlimited)
   - `nse.ingest_current_membership` — populates Nifty500 / Midcap150 / Smallcap250 membership
   - `universe.ingest_sectors` — populates `sector_map`

2. **Universe ordering** — mid-cap → small-cap → large-cap remainder (FVM edge is largest in
   mid/small-caps, so the daily quota fills those first)

3. **Resumable per-stock loop**:
   - Skip if `read_fundamental_asof("Net Profit Annual", asof)` already has data
   - `ingest_financials(store, sym, tc)` — 2 Trendlyne calls
   - `ingest_shareholding(store, sym)` — Screener.in scrape (best-effort, not Trendlyne)
   - Stop on 429 (quota hit) or 403 (stale cookie) with clear error message

**Resumability:** Because already-ingested stocks are skipped based on presence of data in the
store, you can re-run daily and it picks up exactly where it left off. No state file needed.

---

## End-to-end data flow

```
Trendlyne Excel Connect API
  GET /all_stocks/              → fund_stocks table (nsecode → stock_hash)
  GET /quarter/?stock_hash=h    → CSV quarterly financials
  GET /annual/?stock_hash=h     → CSV annual financials
        |
        ↓  parse_financials_csv()
        |
  [{field, period, value}]
        |
        ↓  _knowledge_date_for_period()  (period_end + 45 days)
        |
  [{symbol, statement, basis, period, field, value, knowledge_date}]
        |
        ↓  store.write_fundamentals()  (INSERT OR IGNORE — append-only)
        |
  fundamentals table (SQLite, data/fvm.db)
        |
        ↓  store.read_fundamental_asof(symbol, statement, basis, field, asof)
        |
  {period: value}  — PIT-correct, no look-ahead
        |
        ↓  factors.py  (pillar computations)
        |
  {factor_name: float | None}
```

---

## How factors.py uses the data

`trader/fvm/factors.py` pulls raw series from the store and computes derived metrics. The key
primitive is `_series()`:

```python
def _series(store, symbol, spec, asof, basis="consolidated"):
    statement, field = spec
    d = store.read_fundamental_asof(symbol, statement, basis, field, asof)
    return [(p, v) for p, v in sorted(d.items()) if v is not None]
```

**Crown-jewel factor — floored YoY profit growth:**

```python
g_t = (NP_t - NP_{t-4q}) / max(|NP_{t-4q}|, 1% of TTM_revenue_t)
```

The denominator floor prevents division by zero or meaningless % on tiny/loss bases while
preserving the sign and magnitude of the turnaround. Each `g_t` is winsorized to ±200%.

**Annual fallback (pre-2023 backtest):** Because Trendlyne quarterly data starts ~2023-03,
`floored_yoy_series()` automatically falls back to the same formula on annual net profit /
revenue when no quarterly YoY point exists. Annual data reaches ~2013, enabling backtests through
2019-20 drawdowns without any additional data source.

---

## Known limitations & gotchas

| Issue | Detail |
|-------|--------|
| Quarterly depth hard cap | ~13 quarters from the most recent filing (~2023-03 floor). Do not probe deeper; it's a platform constraint. |
| Cookie expiry | TRENDLYNE_COOKIE is a browser session cookie; expires roughly monthly. Must be refreshed manually by copying from browser DevTools. |
| 403 on data endpoints | Almost always a stale cookie. The token alone cannot unlock `quarter`/`annual`. |
| UA requirement | Non-Google UA returns 403 on data endpoints even with valid token+cookie. Always use the Apps-Script UA. |
| `stock_hash` padding | The hash may contain `====` padding verbatim; pass it as-is in the query string — don't URL-encode or strip it. |
| Basis is always "consolidated" | Standalone financials exist in Trendlyne but the ingest always writes `basis="consolidated"`. Standalone would be a separate ingest pass. |
| knowledge_date is approximate | `period_end + 45 days` is conservative. True announcement dates (available via BSE filings) would give tighter PIT. The 45-day lag means a March quarter is known from ~May 15; in practice it's often declared by late April. |
| Rate limit is per-token, not per-IP | Sharing a token across processes/machines shares the quota. |
| `fund_stocks` must be populated first | `ingest_financials` looks up `get_stock_hash()` — fails if master list hasn't been loaded. Always run `ingest_master` before per-stock ingest. |

---

## Files to copy for another project

The following files are self-contained and directly portable:

| File | What it contains |
|------|-----------------|
| `trader/fvm/data/trendlyne.py` | HTTP client, CSV parser, ingestion helpers |
| `trader/fvm/data/store.py` | SQLite PIT store (FVMStore) |
| `trader/fvm/fields.py` | Semantic field name catalog |
| `trader/fvm/factors.py` | Factor computation over the stored data |
| `scripts/fvm_ingest.py` | End-to-end ingestion runner |
| `docs/FVM_Trendlyne_Fields.md` | Full catalog of all 60 quarterly + 189 annual field names |

Dependencies: `requests`, `python-dotenv`, Python stdlib (`sqlite3`, `csv`, `io`, `calendar`).
No other trader-system dependencies are needed if you stub out `trader.core.logger`.

---

## Quick-start for a new project

```python
from fvm.data.trendlyne import TrendlyneClient, ingest_master, ingest_financials
from fvm.data.store import FVMStore
from fvm import fields as F

store = FVMStore("data/fvm.db")
client = TrendlyneClient()            # reads TRENDLYNE_TOKEN + TRENDLYNE_COOKIE from .env

# Step 1: populate master (once)
ingest_master(store, client)

# Step 2: ingest a stock (2 API calls)
ingest_financials(store, "RELIANCE", client)

# Step 3: PIT read as of a date
d = store.read_fundamental_asof("RELIANCE", *F.NET_PROFIT_Q, "consolidated", "2025-06-01")
# -> {"2025-03": 19123.0, "2024-12": 18765.0, ...}

revenue_series = store.read_fundamental_asof("RELIANCE", *F.TOTAL_REVENUE_A, "consolidated", "2025-06-01")
```
