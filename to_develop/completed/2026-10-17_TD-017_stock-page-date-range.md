# Date-range filter on the stock page (and /chart) — same controls as the dashboard
Written: 2026-10-17 · Tag: TD-017 · Status: DONE

## Source

> okay, another, in the graph page, can i get similar filters as the main dashaborbr for the dates?

— owner, 2026-10-17 (`TODO/TD-017-stock-page-date-range/DETAIL.md`). "Graph page" = the `/stock/<sym>` drilldown
(TD-016 links every stock name to it); `/chart/<sym>` shares `_build_chart`, so it gets the same control.

## Intent

Give `/stock/<sym>` and `/chart/<sym>` the dashboard's range control — quick buttons 1W / 1M / 1Q / 1Y / All plus a
custom from/to date picker — driven by the same URL params (`?range=` or `?from=&to=`, parsed by the existing
`_resolve_range`), so the 30-second body-swap refresh (which re-fetches the current URL) keeps the selection.

Decisions carried by this guide:
- **No range param = today's behaviour, unchanged** (chart from entry − 3 days for an open position else full history;
  last 200 model scores; last 40 signals; all closed trades). An extra **"Auto"** button links to the bare URL and is
  highlighted when no range param is present. The dashboard keeps its own default (All) and is otherwise unchanged.
- With a range: the price chart, its fill/phantom markers, conviction history, closed trades (+ the trade-matched
  benchmark line), and the signals table are limited to the window. Status, latest model reading, open-position detail
  and the per-stock params stay "now".
- Windowed signals: up to 300 rows. Windowed model scores: no row limit (the table keeps only the last 500 per stock —
  a window older than that shows what exists).
- `bench` is preserved across range links/forms on the stock page (as on the dashboard).

Must NOT change: the dashboard's rendered output (its range bar must render byte-identically after the refactor),
`_resolve_range`, `_filter_trades`, any query on the main dashboard, analytics functions, the auto-refresh JS.

## Implementation steps

1. **`trader/ui/template.py` — shared range bar.** Extract the quick-buttons + date-form part of `range_controls` in
   `render_page` into
   ```python
   def _range_bar(base_path: str, range_key: str, lo, hi, now_naive, extra_qs: dict[str, str] | None = None,
                  auto: bool = False) -> str:
   ```
   - buttons: `<a href="{base_path}?range={key}{extra}" class="rbtn[ active]">LABEL</a>` for 1w/1m/1q/1y/all, where
     `extra` is `&k=v` for each `extra_qs` item (`urllib.parse.quote` the values); when `auto=True` prepend an
     "Auto" button linking to `base_path` + (`?` + extra pairs if any), active when `range_key == "auto"`.
   - date form: `method="GET" action="{base_path}"`, `from`/`to` inputs pre-filled exactly like today
     (`lo` → `%Y-%m-%d` or empty; `to` = `(hi or now_naive)`), one hidden input per `extra_qs` item, Apply button active
     when `range_key == "custom"`.
   - wrapped in the existing `<span class="rangebar">` with the `Range:` label.
   `render_page` builds its `range_controls` from `_range_bar("/", _range_key, _lo, _hi, now.replace(tzinfo=None),
   extra_qs={"bench": _bench_key} …)` + its existing `vs:` benchmark buttons — **keep the dashboard's exact current
   HTML**: today the quick buttons append `&bench=…` only when the bench is not the default, while the form always
   carries a hidden bench input; reproduce that precisely (e.g. separate `link_qs` / `form_hidden` arguments if
   needed). Write a throwaway check rendering the dashboard before/after (same fixture) to confirm the range bar
   string is identical; the existing `tests/test_ui_render_page.py` must pass unchanged.

2. **`_build_chart(instrument, config, width=1100, height=480, lo=None, hi=None)`** — new optional IST-naive bounds.
   - When `lo` is given, the candle query uses `timestamp >= lo.isoformat()` instead of the entry−3d / 2000-01-01 rule;
     when `hi` is given add `AND timestamp <= hi.isoformat()`. Candle timestamps are exchange (IST) time — use `lo/hi`
     as is.
   - Fill markers and phantom markers: when a window is set, drop orders / phantom signals whose time maps outside
     `[timestamps[0], timestamps[-1]]` (compare the same `[:16]` string prefix `_find_candle_idx` uses) instead of
     letting them clamp to the chart edges. No window → current behaviour exactly.
   - Entry line / levels for an open position: unchanged (they are "now" facts); if the entry is before the window the
     entry index stays 0, as `_find_candle_idx` already returns.

3. **`render_stock_page(instrument, bot_state, risk, store, config, bench=None, range_params=None)`**
   - `lo, hi, label, key = _resolve_range(range_params)` only when `range_params` contains `range`, `from` or `to`;
     otherwise `key = "auto"` and `lo = hi = None` (today's behaviour everywhere below).
   - Range bar: `_range_bar(f"/stock/{quote(sym, safe='')}", key, lo, hi, now_naive, extra_qs={"bench": bench} if bench
     else None, auto=True)`, placed in the page header area next to the existing title/status (follow the dashboard's
     header placement; reuse the `.rangebar` CSS — no new CSS). Show the active `label` (or "Auto") as dim text.
   - Chart: `_build_chart(instrument, config, width=1100, height=420, lo=lo, hi=hi)`.
   - Conviction: windowed → new `_read_model_scores_window(db_path, instrument, lo, hi)` (oldest-first, IST bounds,
     no limit); auto → unchanged `_read_model_scores(..., limit=200)`.
   - Closed trades: windowed → `_filter_trades(matched, lo, hi)` AFTER `_load_matched_trades` (FIFO on the full set,
     as the dashboard does); the trade-matched benchmark line uses the windowed trades. Section heading gets
     `· {label}` like the dashboard's Orders heading.
   - Signals: windowed → `logged_at` between the process-local bounds computed exactly as `render_page` does
     (`lo - _NAIVE_TO_IST_DELTA`, `hi - _NAIVE_TO_IST_DELTA`), `ORDER BY id DESC LIMIT 300`; auto → unchanged LIMIT 40.

4. **`render_chart_page(instrument, store, config, range_params=None)`** — same param handling (auto when absent),
   `_build_chart(..., lo=lo, hi=hi)`, and a range bar with `base_path=f"/chart/{quote(sym, safe='')}"`, `auto=True`.

5. **`trader/ui/server.py`** — pass `range_params=request.args.to_dict()` to `render_stock_page` (keep the existing
   `bench=` argument) and to `render_chart_page`.

## Tests required

New **`tests/test_ui_stock_range.py`** (reuse the `ctx` fixture / `_order` helper from `tests/test_ui_render_page.py`
as `tests/test_ui_stock_links.py` does; seed candles for the instrument the way existing chart/stock-page tests do —
grep `render_stock_page` in tests for a harness):
- `test_stock_page_has_range_bar_auto_active` — no params → page contains `class="rangebar"`, an active "Auto"
  button, and links `/stock/SYM?range=1m` etc.
- `test_stock_page_window_filters_trades_and_signals` — seed one round trip + signal ~40 days ago and one ~2 days ago;
  `range=1w` → only the recent trade/signal appear; `range=all` → both.
- `test_custom_from_to` — `from`/`to` around the old trade → only the old one appears; the date inputs are pre-filled.
- `test_bench_preserved` — `bench=gold&range=1m` → range links carry `bench=gold`.
- `test_chart_page_range` — `/chart` render with `range=1w` contains the range bar and still renders (or the
  not-enough-candles message) without error.
- `test_dashboard_range_bar_unchanged` — render the dashboard with and without `range=1m`, assert the range-bar span
  equals the pre-refactor markup (hard-code the expected string for one case from the current code before editing).

Whole suite green: `python -m pytest -q` (only ISS-11 may fail 09:15–15:30 IST).

## Acceptance checklist
- [ ] dashboard output unchanged (existing UI tests + the new byte-identity test)
- [ ] /stock and /chart: Auto (default, today's behaviour) + 1W/1M/1Q/1Y/All + custom dates; selection survives refresh (URL params)
- [ ] windowed: chart + markers, conviction, closed trades (+ benchmark line), signals; "now" sections untouched
- [ ] FIFO matching on the full order set before windowing; time-base handling as specified (candles/scores IST, signals local)
- [ ] only template.py, server.py and the new test file touched; no new CSS
- [ ] full pytest green (apart from ISS-11 in its window)

## Completion record
- **Completed:** 2026-10-18 — implementer (trader-implementer, sonnet); interrupted by a session restart and resumed with its partial edits intact; validated by the main session (`.venv/bin/python -m pytest -q` 565 passed; diff = template.py + server.py + new test file only).
- **Commit:** see `git log -- to_develop/completed/2026-10-17_TD-017_stock-page-date-range.md`.
- **Deviations:** `_range_bar` takes two extra optional kwargs (`link_qs`, `tail_html`) to reproduce the dashboard's exact markup (quick links add `&bench=` only for a non-default benchmark; the "vs:" buttons sit inside the span). Byte-identity verified on 6 param sets before/after + a hard-coded test. `/chart` shows the bar in a new meta row (also on the not-enough-candles path).
- **Notes:** model-score history is capped at 500 rows per stock, so long windows show what exists.
