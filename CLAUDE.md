# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
python budget_app.py
```

Install external dependencies:

```bash
python -m pip install customtkinter tkcalendar
```

`sqlite3`, `tkinter`, `os`, and `datetime` are Python standard library — no install needed.

## Architecture

Single-file application (`budget_app.py`) with three classes and one standalone widget:

**`DatePickerButton(ctk.CTkFrame)`** — custom date-picker widget (replaces `tkcalendar.DateEntry`).
- Renders a `CTkEntry` (editable) + `📅` button side-by-side.
- Button opens a `tkcalendar.Calendar` in a `Toplevel` with `grab_set()` — this is intentional. `DateEntry` inside `CTkScrollableFrame` loses grab to the scroll frame, breaking month/year navigation buttons. The custom `Toplevel` + `grab_set()` pattern fixes that.
- External interface matches `DateEntry`: `.get()` → `"YYYY-MM-DD"` string; `.set_date(datetime.date | str)`.

**`Database`** — all SQLite logic, no UI coupling.
- Opens/creates `data/account_book.db` relative to the script's directory.
- Two tables: `transactions` (거래 내역) and `settings` (key-value store, currently only `carryover`).
- Key methods: `add_transaction`, `update_transaction`, `delete_transaction`, `get_all_transactions(year, month)`, `get_summary(year, month)`, `get_balance_before(year, month)`, `get_distinct_years()`.
- All filter methods accept `year=None, month=None`; `None` = no filter (full scan).
- SQLite date filtering uses `strftime('%Y', date)` / `strftime('%m', date)` (zero-padded) — not `YEAR()`/`MONTH()` which are MariaDB-only.

**`BudgetApp(ctk.CTk)`** — the entire GUI, owns a `Database` instance.
- Layout: fixed-width left panel (314 px, input form) + expanding right panel.
- Right panel rows: `0` summary cards → `1` filter bar → `2` settings bar (font slider) → `3` list frame.
- UI is built by `_build_layout` → `_build_left_panel` → `_build_right_panel` → `_build_filter_bar` → `_build_settings_bar` → `_apply_treeview_style` → `_build_treeview`, called sequentially from `__init__`.
- Startup filter: `_filter_year` / `_filter_month` default to the current month.
- Edit state: `_edit_mode` / `_edit_id`; toggled by `_enter_edit_mode` / `_exit_edit_mode` which also swap button labels/colors and disable the delete button while editing.
- `load_data(year, month)` is the single refresh entry point — stores raw DB tuples in `self._current_rows`, calls `_render_rows`, updates summary cards.
- `_render_rows(rows)` clears and re-inserts all treeview rows. Uses `iid=str(db_id)` so `int(tree.selection()[0])` recovers the real DB PK; `values[0]` is a display-only sequential `No.` starting from 1.
- `_on_sort(col)` sorts `self._current_rows` in-place and re-calls `_render_rows`; `_sort_asc` dict persists toggle direction per column.
- Font-size slider calls `ttk.Style.configure` then `_render_rows` to force a treeview redraw (ttk style changes don't auto-redraw).

## Key Design Decisions

- **Treeview is `ttk`, not customtkinter** — `ttk.Treeview` with a `clam`-based dark style applied in `_apply_treeview_style`. Must be called before `_build_treeview`. The same method is called by the font-size slider to update `rowheight`.
- **Treeview `iid` = DB PK string** — no separate id map needed; `int(selection[0])` gives the real DB id directly.
- **Monthly carryover auto-calculation** — when year+month is active, `get_balance_before(year, month)` returns `stored_carryover + all_prior_income − all_prior_expense`. Full/year-only views use the stored `carryover` setting directly.
- **`CATEGORIES` dict** (module-level) is the single source of truth for category lists. To add/rename a category, change only this dict.
- Amount fields strip commas before parsing so formatted values like `1,000` can be re-entered without error.
- After add/delete, `_refresh_year_combo()` syncs the filter year combobox with actual DB contents.
