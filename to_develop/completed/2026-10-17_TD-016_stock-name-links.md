# Every stock name on the dashboard links to its /stock/<sym> drilldown
Written: 2026-10-17 · Tag: TD-016 · Status: DONE

## Source

> okay, quick fix for the UI, anywhere there is the stock name ,it shoudl redirectyt me to the stock graph page that we built.

— owner, 2026-10-17 (`TODO/TD-016-stock-names-link-to-drilldown/DETAIL.md`).

## Intent

The `/stock/<sym>` drilldown (`render_stock_page`, route in `trader/ui/server.py`) is linked from Open Positions,
Per-Stock Performance and the Watchlist only. Make every other place where `trader/ui/template.py` prints a stock name
link there too, via ONE helper, and URL-encode the symbol (names like `M&MFIN` contain `&`).

Must NOT change: page layout/columns, CSS, the auto-refresh JS, the health strip (its badges are already whole-badge
anchors to `#signals` etc. — nested links are invalid HTML, leave them), SVG `<title>` hover text, the stock page's own
`<h1>`/`<title>`, the `/chart/<sym>` page, any data/query logic.

## Implementation steps

1. **`trader/ui/template.py`** — add near the other small render helpers (e.g. next to `_badge`):
   ```python
   def _stock_link(sym: str) -> str:
       """Stock name → its /stock/<sym> drilldown (TD-016). URL-encodes the path (M&MFIN) and HTML-escapes the text."""
       return f"<a href='/stock/{quote(sym, safe='')}' class='chart-link'>{escape(sym)}</a>"
   ```
   using `from urllib.parse import quote` and `from html import escape` (add the imports only if missing; if the module
   already imports `html`, use `html.escape`).
2. Replace the plain `{sym}` cell text with `{_stock_link(sym)}` at:
   - Open Positions — pending-order rows (`for inst in pending_orders:` … `f"<td>{sym}</td><td>—</td>…"`, ~line 2232)
   - Orders table (`f"<td>{sym}</td>"`, ~2283)
   - Closed trades table (`f"<td>{sym}</td>"`, ~2345)
   - Recent Signals (`f"<td>{sym}</td>"`, ~2485)
   - Filtered Signals (`f"<td>{sym}</td>"`, ~2519)
   - Capital card loss-block line (~1639): `", ".join(f"{_stock_link(k.split(':')[-1])} ({v})" …)`
   Keep any badge/suffix that follows the name in the same cell.
3. Switch the three EXISTING hand-written links (`<a href='/stock/{sym}' class='chart-link'>{sym}</a>` in Open
   Positions ~2211, Per-Stock Performance ~2444, Watchlist `{ticker}` ~2713) to `_stock_link(...)` so encoding is uniform.
   Leave the `/chart` page's "`{sym} drilldown`" link text as is but URL-encode its href with `quote(sym, safe='')`.
4. Finally grep `template.py` for `<td>{sym}</td>`, `<td>{ticker}</td>` and other bare `{sym}` / `{ticker}` /
   `split(":")[-1]` renders inside the MAIN dashboard (`render_page`) that are visible text in a table cell or list and
   not already inside an `<a>`, and convert them the same way. List every additional site you converted (or chose not to,
   with the reason) in your report. Do not touch `render_stock_page` sections that show the page's own symbol.

## Tests required

New **`tests/test_ui_stock_links.py`**:
- `test_stock_link_encodes_and_escapes` — `_stock_link("M&MFIN")` contains `href='/stock/M%26MFIN'` and text `M&amp;MFIN`;
  `_stock_link("QUESS")` → `href='/stock/QUESS'`.
- `test_rendered_tables_link_symbols` — render the dashboard with the existing harness from
  `tests/test_ui_render_page.py` (reuse its fixture/helpers: build a DB with at least one order, one closed round trip and
  one signal for a symbol, as that file already does — if it already seeds those, reuse as is) and assert that every
  `<td>SYMBOL</td>` occurrence is gone for the seeded symbol and `/stock/SYMBOL` appears. If the existing harness cannot
  seed one of the tables without new fixture code, cover the tables it can and say which ones in the report.
- `tests/test_ui_render_page.py` must stay green unchanged (only ISS-11 may fail 09:15–15:30 IST).

Whole suite green: `python -m pytest -q`.

## Acceptance checklist
- [ ] one `_stock_link` helper; all listed sites + existing links use it; hrefs URL-encoded
- [ ] health strip, SVG titles, stock-page own symbol untouched; no layout/CSS change
- [ ] new tests passing; full suite green (apart from ISS-11 in its window)
- [ ] only `trader/ui/template.py` and the new test file touched (plus the server-free render harness reuse)

## Completion record
- **Completed:** 2026-10-17 — implementer (general-purpose, sonnet); validated by the main session (diff = helper + 10 call sites; `python -m pytest -q` 559 passed); released release-20261017f and checked on the live page.
- **Commit:** see `git log -- to_develop/completed/2026-10-17_TD-016_stock-name-links.md`.
- **Deviations:** imports as `_quote` + existing `_html.escape` (module convention) instead of bare `quote`/`escape`.
- **Notes:** left as plain text on purpose — health-strip badge lists (whole badge is already an anchor), hidden form input,
  stock page's own symbol. Pending-order rows and the loss-block line have no render test (harness can't seed them).
