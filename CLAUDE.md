# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**uexinfo** — Interactive CLI (REPL) for Star Citizen trading data. Queries the UEX Corp 2.0 REST API and (Phase 4) scrapes sc-trade.tools to display commodity prices, trade routes, and flight plans in the terminal.

## Commands

```bash
# Install in editable mode (activate venv first)
pip install -e .

# Run the REPL
python -m uexinfo
# or after install:
uexinfo

# Run tests (pytest, no tests written yet)
pytest

# Run a single test file
pytest tests/path/to/test_file.py
```

No Makefile or task runner. No CI pipeline configured.

## Architecture

The app is a **REPL loop** that parses `/command args` lines and dispatches to registered handlers. All state lives in `AppContext` (config dict + CacheManager instance).

### Layer map

| Layer | Location | Role |
|---|---|---|
| REPL entry | `uexinfo/cli/main.py` | Boot, `AppContext`, prompt loop |
| Parser | `uexinfo/cli/parser.py` | `/cmd args` → `(name, [args])` via `shlex` |
| Command registry | `uexinfo/cli/commands/__init__.py` | `@register` decorator + `dispatch()` |
| Commands | `uexinfo/cli/commands/*.py` | One file per command |
| Tab completion | `uexinfo/cli/completer.py` | Context-aware, static subcommand map |
| API client | `uexinfo/api/uex_client.py` | REST → UEX Corp 2.0 (`https://uexcorp.space/api/2.0`) |
| Cache | `uexinfo/cache/manager.py` | Fetch → parse → save JSON in `~/.uexinfo/` |
| Data models | `uexinfo/cache/models.py` | `StarSystem`, `Planet`, `Terminal`, `Commodity` dataclasses |
| Config | `uexinfo/config/settings.py` | Read/write `~/.uexinfo/config.toml` |
| Display | `uexinfo/display/` | Shared Rich console, color constants, table helpers |

### Adding a new command

1. Create `uexinfo/cli/commands/mycommand.py`
2. Use the `@register("mycommand", "alias")` decorator from `commands/__init__.py`
3. Handler signature: `def handle(args: list[str], ctx: AppContext) -> None`
4. Register it by importing the module in `commands/__init__.py`
5. Add tab-completion subcommands in `completer.py`'s static map

### Data flow for static data (systems, terminals, commodities)

`CacheManager.load()` → check file mtime against TTL → if stale, call `UEXClient` → parse into dataclasses → save JSON to `~/.uexinfo/` → cache in memory. On failure, falls back to existing disk cache.

### Color conventions (Rich)

- **cyan** — UEX Corp data (`colors.UEX`)
- **orange1** — sc-trade.tools cross-referenced data (`colors.SCTRADE`)
- **bold green/red** — profit / loss (`colors.PROFIT`, `colors.LOSS`)

Always use constants from `uexinfo/display/colors.py`, not raw color strings.

## Key docs

- `docs/architecture.md` — full system design, data flow, roadmap
- `docs/api-uex.md` — UEX Corp 2.0 API reference
- `docs/commands.md` — complete command manual
- `docs/api-sctrade.md` — Phase 4 scraping strategy (BeautifulSoup / Playwright)

## Current state (Phase 1 complete)

Implemented: `/help`, `/config`, `/go`, `/lieu`, `/select`, `/refresh`
Stubs (Phase 2–4): `/trade`, `/route`, `/plan`, `/info`

Phase 2 priority: `/trade buy|sell|best|compare` using live `UEXClient.get_prices()`.
