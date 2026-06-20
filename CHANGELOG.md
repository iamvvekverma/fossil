# Changelog

## 0.2.0 — 2026-06-19

### Added

- **Rich terminal output** — `fossil explain` now renders beautiful panel-based reports with colored sections, confidence progress bars, and formatted tables matching the UX spec (§4.1).
- **`fossil scan` Rich table output** — Scan results display in a formatted table with file paths, language, dead-since date, and color-coded confidence scores (§4.2).
- **`fossil clean` Rich backlog** — Prioritized deletion backlog with numbered entries and confidence scores.
- **Parallel scan processing** — `fossil scan` and `fossil clean` now use `ThreadPoolExecutor` for analyzing files in parallel when the candidate count exceeds 10, with a Rich progress bar showing scan progress.
- **`--plain` flag** — All commands support `--plain` for plain ASCII output without Rich formatting, suitable for piping and screen readers.
- **`--remote` flag** — `fossil explain` accepts `--remote github|gitlab|none|auto` to force remote type detection.
- **`--no-color` flag** — Properly passed through to Rich renderer; also respects `NO_COLOR` and `FOSSIL_NO_COLOR` environment variables.
- **`.fossil.toml` project config** — Teams can commit project-level configuration (language filters, exclude patterns, confidence thresholds, PR settings) to the repo root.
- **`fossil cache stats`** — New subcommand showing cache location, size, and entry counts.
- **PR cache table** — SQLite cache now includes `pr_cache` table for caching GitHub/GitLab PR lookups.
- **Schema versioning** — Cache database includes `schema_version` table for future migration support.
- **Auto-pruning** — Cache automatically prunes entries older than `cache_ttl_hours` when cache exceeds 100MB.
- **Cache corruption recovery** — Corrupted cache files are silently deleted and rebuilt.
- **TOML config parsing** — User config file now parsed via `tomllib` (Python 3.11+) instead of manual line parsing.
- **Environment variable overrides** — `FOSSIL_DEFAULT_DEPTH`, `FOSSIL_LOG_LEVEL`, and other env vars override config values.
- **Comprehensive test suite** — 85 tests across 9 test files covering analyzers, git miner, patterns, scoring, cache, config, repo utilities, and end-to-end CLI commands.

### Changed

- `rich` moved from optional dependency to core dependency.
- Version bumped to 0.2.0.
- Config manager now supports nested TOML sections.

## 0.1.0 — 2026-06-19

### Added

- Initial release.
- `fossil explain <file>` with JSON/plain output, cache support, and exit codes.
- Python static analyzer using `ast` for imports, symbols, calls, dynamic imports, and reflection.
- Conservative text-fallback analysis for JavaScript, TypeScript, Java, Go, docs, config files.
- Git history mining for death commit, original author, last modification, shallow clone warning.
- Temporary hold detection for TODO/FIXME/DEPRECATED patterns with date/version/PR condition verification.
- Confidence scoring with weighted signals and risk labels.
- `fossil scan [directory]` with threshold filtering and JSON output.
- `fossil clean [directory]` with deletion backlog output.
- `fossil cache clear` and `fossil config set/show`.
- SQLite cache for analysis results.
- 5 initial tests.
