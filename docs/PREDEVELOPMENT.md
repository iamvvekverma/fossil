# fossil — Pre-Development Documentation
### Complete Technical Specification for Dead Code Forensics CLI

---

## 1. Project Overview

### Elevator Pitch

`fossil` is a command-line forensics tool that goes beyond detecting dead code to explaining its *history* — when it died, what killed it, who wrote it, why it existed, and whether it is genuinely safe to delete — by combining static analysis, git history mining, and optional LLM narration into a single terminal command that answers in under 3 seconds.

### Problem Statement

Dead code is universally present in production codebases. Every mature project accumulates it: files made obsolete by migrations, functions replaced but never removed, modules that were "kept temporarily" and then forgotten. Existing tools — `vulture`, `deadcode`, ESLint's `no-unused-vars`, IntelliJ's inspections — identify *what* is dead. None of them explain *why*.

This gap matters because developers hesitate to delete dead code they don't understand. Was this file intentionally disabled, or accidentally orphaned? Is it used via reflection or dynamic import? Was it kept for a reason that may still apply? Without answers, developers leave dead code in place indefinitely. `fossil` answers the forensic question, not just the static question.

### Target Users / Personas

**Persona 1 — The Cleanup Engineer**
A senior developer assigned to reduce codebase complexity before a major refactor. Needs to understand the history of every suspicious file before touching it. Has no time to manually trace git blame across hundreds of files.

**Persona 2 — The Tech Lead Auditor**
Conducting a pre-sprint technical debt audit. Needs a prioritized list of dead code with deletion confidence scores so the team can plan cleanup work with known risk levels.

**Persona 3 — The New Joiner**
Onboarding to an unfamiliar codebase. Encounters files with no obvious purpose and needs to understand if they are abandoned legacy code or intentionally dormant systems.

**Persona 4 — The Platform/SRE Engineer**
Responsible for a large microservices repo with years of accumulated dead modules. Needs batch scanning and machine-readable output to integrate fossil into CI pipelines and track cleanup progress over time.

### Key Goals

- Identify dead code with static analysis across multiple languages.
- Mine git history to determine when code died and what killed it.
- Parse commit messages and PR links to reconstruct original intent and replacement context.
- Detect deferred deletion patterns ("keep for now", "TODO: remove after X") and verify whether the deferral condition has been met.
- Produce a human-readable confidence score (0–100%) with a per-signal breakdown.
- Generate a deletion PR when confidence is high and the developer passes `--yolo`.
- Work fully offline except for PR creation and optional LLM narration.
- Run in under 3 seconds for a single-file `fossil explain`.

### Explicit Non-Goals

- `fossil` will **NOT** automatically delete code without explicit user action (`--yolo` still requires a commit and PR, not a silent `rm`).
- `fossil` will **NOT** function as a linter, style checker, or code formatter.
- `fossil` will **NOT** track code coverage — it detects structural dead code, not execution-time dead paths.
- `fossil` will **NOT** refactor or suggest rewrites; it identifies candidates for removal only.
- `fossil` will **NOT** scan binary files, images, generated protobuf files, or build artifacts.
- `fossil` will **NOT** provide a web UI, dashboard, or SaaS offering; it is a pure CLI tool.
- `fossil` will **NOT** function as a security scanner or vulnerability detector.
- `fossil` will **NOT** analyze code inside git submodules in Phase 1 or 2.
- `fossil` will **NOT** support repositories without git history (no-VCS projects).
- `fossil` will **NOT** send source code to external services unless the user explicitly enables `--include-code` for LLM narration.

---

## 2. Functional Requirements

> **Legend:** [M] Must-have · [S] Should-have · [N] Nice-to-have

---

### 2.1 Single-File Forensic Report

**[M]** As a developer, I want to run `fossil explain src/billing/legacy_processor.py` and receive a structured forensic report showing when the file became dead, what commit killed it, its original intent, and whether it is safe to delete — so I can make a deletion decision without manually tracing git history.

**Edge cases:**
- File does not exist → exit 2, print `Error: File not found: src/billing/legacy_processor.py`
- File exists but has no git history (untracked or newly added) → report `Status: UNTRACKED — No git history. Cannot determine death date.` Confidence: N/A
- File exists in git but repo has no remote → disable PR features, note `No remote detected. PR generation unavailable.`
- File is inside a `.gitignore`d directory → warn `Warning: File is gitignored. Analysis may be incomplete.`
- File is a symlink → resolve symlink, analyze the target, note that the path is a symlink

---

### 2.2 Static Deadness Confirmation

**[M]** As a developer, I want fossil to statically confirm that a file has zero call sites, zero import references, and zero dynamic references across the entire codebase — so I can trust that the file is structurally dead and not merely poorly documented.

**Edge cases:**
- Dynamic import detected (`importlib.import_module("billing.legacy_processor")`) → confidence penalty; report `Dynamic import detected: importlib — cannot guarantee absence of runtime usage`
- String-based import (`__import__("legacy_processor")`) → same as above
- `getattr` usage that references the module name as a string → flag with `Reflection risk: getattr pattern detected`
- File is referenced only from test files → note `Test-only references: 2 test files import this. Main codebase has 0 references.` — does NOT make file "live" but reduces confidence by 10 points
- File is referenced from a README or documentation file → note `Documentation reference detected: README.md:42`
- Language not supported → use generic text-based reference search; flag `Language: UNKNOWN — using text-search fallback. Static analysis incomplete.`

---

### 2.3 Git History Mining

**[M]** As a developer, I want fossil to traverse git log to identify the exact commit that made this file dead — the commit where calling code was removed or replaced — so I have a precise reference point for the deletion decision.

**Edge cases:**
- File has commits but no clear "death commit" (gradual fade with no single replacement) → report `Death commit: AMBIGUOUS — File usage declined gradually. Last reference removed in commit abc1234.`
- Commit history is very long (>5000 commits) → traverse up to `--depth` limit (default 500); warn `Warning: History truncated at 500 commits. Use --depth 2000 for deeper traversal.`
- File was deleted and re-added in history → report each deletion cycle; flag `Note: File has been deleted and re-added 2 times in history. Analyzing most recent lifecycle.`
- Shallow clone (CI environment) → detect shallow clone, warn `Warning: Shallow git clone detected. History may be incomplete. Run 'git fetch --unshallow' for full analysis.`
- Merge commits obscure the actual author → traverse to the original branch commit; attribute correctly

---

### 2.4 Commit and PR Message Parsing

**[S]** As a developer, I want fossil to extract the PR number and title from commit messages, and fetch the PR title and body from GitHub/GitLab if a token is configured — so I can read the original rationale for the replacement without leaving the terminal.

**Edge cases:**
- Commit message has no PR number → skip PR lookup; report `PR: Not referenced in commit message`
- PR number found but GitHub token not configured → report `PR #441 referenced. Configure GITHUB_TOKEN to fetch PR details.`
- GitHub API returns 404 for PR → report `PR #441: Not found on remote. Repository may be private or PR was deleted.`
- GitHub API rate limit hit → use cached result if available; otherwise skip and note `GitHub API rate limit reached. PR details unavailable.`
- GitLab remote detected (gitlab.com or self-hosted) → use GitLab API instead; require `GITLAB_TOKEN`
- Monorepo with multiple remotes → prompt user to specify: `fossil explain path --remote github`

---

### 2.5 Temporary Hold Pattern Detection

**[M]** As a developer, I want fossil to detect "keep for now", "TODO: remove after X", "temporary — remove when Y ships" patterns in comments within the file, and then check whether condition X or Y has since been met — so I know whether the deferral is still valid or has been forgotten.

**Patterns to detect (case-insensitive):**
- `TODO: remove after <condition>`
- `FIXME: delete when <condition>`
- `keep for now`, `keep around until <condition>`
- `temporary`, `temp code`, `temp fix`
- `DEPRECATED`, `@deprecated`
- `will be removed in <version/date>`

**Condition verification:**
- If condition mentions a PR number → check if that PR is merged
- If condition mentions a version number → check git tags for that version
- If condition mentions a date → compare to today
- If condition is narrative and unresolvable → report `Condition: UNVERIFIABLE — "until the new billing system is stable" (manual review required)`

**Edge cases:**
- Pattern found but condition cannot be parsed → confidence penalty 10 points; report as unverifiable
- Multiple patterns in same file → report all of them
- Pattern in a test file for this module → report separately

---

### 2.6 Confidence Score

**[M]** As a developer, I want to see a 0–100% confidence score for whether it is safe to delete the file, with a per-signal breakdown — so I can understand exactly what is driving the score and override it if needed.

**Confidence signal weights:**

| Signal | Weight | Direction |
|--------|--------|-----------|
| Zero call sites (static) | +30 | Positive |
| No dynamic references | +20 | Positive |
| Death commit identified | +15 | Positive |
| Temporary hold resolved | +10 | Positive |
| No reflection patterns | +10 | Positive |
| File age > 90 days dead | +8 | Positive |
| PR/migration context found | +7 | Positive |
| Dynamic import detected | −30 | Negative |
| Reflection/getattr detected | −20 | Negative |
| Test file references found | −10 | Negative |
| "Keep for now" unresolved | −15 | Negative |
| Language unknown (fallback) | −15 | Negative |
| File modified < 30 days ago | −20 | Negative |
| Death commit ambiguous | −10 | Negative |

**Risk labels:**
- 85–100%: High Confidence — Low Risk
- 70–84%: Medium-High Confidence — Low-Medium Risk
- 55–69%: Medium Confidence — Medium Risk
- Below 55%: Low Confidence — High Risk (do not auto-delete)

---

### 2.7 Directory Scan

**[M]** As a developer, I want to run `fossil scan ./src` and receive a ranked table of all dead files in the directory with their confidence score and dead-since date — so I can understand the full scope of cleanup work in one command.

**Edge cases:**
- Directory contains no supported language files → `No supported source files found in ./src. Supported: Python, JavaScript, TypeScript, Java, Go.`
- No dead code found → exit 4 with `✓ No dead code found above 70% threshold.` (exit 4 is machine-readable for CI)
- Very large directory (>100k files) → show progress bar; auto-suggest `--language py` to narrow scope; warn of estimated completion time
- Mix of languages in directory → analyze all by default; group output by language in table

---

### 2.8 JSON Output

**[S]** As a developer, I want `fossil explain --json` and `fossil scan --json` to produce machine-readable JSON output — so I can pipe results into scripts, dashboards, or CI pipeline gates.

**Edge cases:**
- Combined with Rich output flags → `--json` always wins; no color codes in output
- Error states must also be JSON when `--json` is active: `{"error": "File not found", "code": 2}`

---

### 2.9 Deletion PR Generation

**[N]** As a developer, I want to run `fossil explain src/billing/legacy_processor.py --yolo` and have fossil create a branch, delete the file, commit it, push, and open a PR on GitHub/GitLab — so I can remove dead code without leaving my terminal.

**Edge cases:**
- Confidence below 90% → require `--force-yolo` and warn: `Confidence is 74%. --yolo blocked below 90%. Use --force-yolo to override.`
- `GITHUB_TOKEN` not set → exit 1 with setup instructions
- Branch already exists on remote → append `-2`, `-3` suffix; warn user
- File already absent in working tree → `File is already deleted. Nothing to do.`
- PR creation fails due to permissions → exit with API error message; local branch and commit are preserved

---

### 2.10 LLM Narration

**[N]** As a developer, I want `fossil explain --narrate` to produce a natural-language paragraph explaining the forensic findings — so I can share context with non-technical stakeholders or teammates unfamiliar with the codebase.

**Edge cases:**
- LLM API key not configured → `--narrate requires a configured LLM provider. Run: fossil config set llm_provider openai`
- LLM API timeout → fall back to structured output; print `Warning: LLM narration timed out. Showing structured output only.`
- Narration mode never sends raw source code to LLM by default; only structured metadata
- `--include-code` flag must be explicitly passed to include source lines in the LLM prompt; user is warned with a consent prompt

---

### 2.11 Result Caching

**[S]** As a developer, I want fossil to cache analysis results in `.fossil/cache.db` indexed by file path and current git HEAD hash — so repeated runs on the same file in the same commit state return instantly.

**Edge cases:**
- Cache corrupted → silently delete and rebuild: `Warning: Cache corrupted. Rebuilding.`
- Cache exceeds 100MB → auto-prune entries older than `cache_ttl_hours` (default 24h)
- `--no-cache` flag → skip read and write for this run
- Different git HEAD → cache miss; full re-analysis

---

## 3. Technical Architecture

### 3.1 Recommended Tech Stack

| Layer | Choice | Justification |
|-------|--------|---------------|
| Language | Python 3.11+ | Best ecosystem for AST/static analysis, git tooling, and LLM integration; `ast`, `tree-sitter`, `GitPython` are mature libraries |
| CLI framework | Typer 0.12+ | Type-hint-driven CLI definitions, auto-generated `--help` and shell completions, cleaner than raw Click |
| Terminal output | Rich 13+ | Industry standard for beautiful terminal formatting: panels, tables, progress bars, color, markup |
| Static analysis | tree-sitter 0.21+ | Language-agnostic, C-speed parsing, supports 50+ languages, used by GitHub Semantic and Neovim |
| Python analysis | `ast` (stdlib) + tree-sitter | Python's own `ast` module for deep Python analysis; tree-sitter as the cross-language layer |
| Git operations | GitPython 3.1+ | Programmatic git access without subprocess shell injection risk; mature API for log, blame, diff |
| GitHub API | PyGithub 2.x | Well-maintained, handles auth, pagination, PR creation |
| GitLab API | python-gitlab 4.x | Official GitLab client library |
| LLM narration | litellm 1.x | Unified interface across OpenAI, Anthropic, Ollama, Gemini; user brings their own key |
| Local cache | SQLite (stdlib) | Zero dependency, file-portable, queryable; perfect for local CLI caching |
| Config | `tomllib` (stdlib, Python 3.11+) | Human-readable TOML; standard for Python tooling (Black, Ruff, etc.) |
| Data models | Pydantic v2 | Runtime validation, auto-serialization to JSON, clean model definitions |
| Testing | pytest + tmp_path | Ephemeral git repo fixtures via `tmp_path`; fast, parallelizable |
| Distribution | PyPI + Homebrew | `pip install fossil-cli`; `brew install fossil` via a tap formula |

> **Assumption:** Python 3.11+ is the minimum target. This gives us `tomllib` in stdlib and `ExceptionGroup` for clean error handling.

---

### 3.2 System Architecture (Text Description)

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLI LAYER                                   │
│   cli.py  →  commands/explain.py | scan.py | clean.py | config.py  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
           ┌───────────────▼───────────────┐
           │         CORE ENGINE           │
           │                               │
   ┌───────▼────────┐    ┌────────────────▼──────┐
   │ Static Analysis│    │   Git History Miner    │
   │    Engine      │    │   (miner.py)           │
   │ (analyzers/)   │    │                        │
   │                │    │  - git log traversal   │
   │ - call sites   │    │  - death commit finder │
   │ - dynamic refs │    │  - blame integration   │
   │ - reflection   │    └────────────┬───────────┘
   └───────┬────────┘                │
           │                ┌────────▼───────────┐
           │                │  Commit/PR Parser  │
           │                │  (pr_parser.py)    │
           │                │                    │
           │                │ - PR# extraction   │
           │                │ - GitHub/GitLab API│
           │                │ - migration intent │
           └────────┐       └────────┬───────────┘
                    │                │
           ┌────────▼────────────────▼───────┐
           │       Pattern Detector           │
           │       (detector.py)              │
           │                                  │
           │  "TODO: remove", "keep for now" │
           │  condition verification          │
           └────────────────┬────────────────┘
                            │
           ┌────────────────▼────────────────┐
           │       Confidence Scorer          │
           │       (confidence.py)            │
           │                                  │
           │  Aggregates all signals → 0-100 │
           │  score + risk label              │
           └────────────────┬────────────────┘
                            │
                ┌───────────▼──────────────┐
                │  (Optional) LLM Narrator │
                │  (llm.py via litellm)    │
                └───────────┬──────────────┘
                            │
           ┌────────────────▼────────────────┐
           │        Output Renderer           │
           │  terminal.py  |  json_renderer  │
           └────────────────┬────────────────┘
                            │
                    ┌───────▼────────┐
                    │  Cache Store   │
                    │  (SQLite)      │
                    └───────────────┘

External Services (optional, network):
  ├── GitHub API  — PR title/body fetch + PR creation (--yolo)
  ├── GitLab API  — same, for GitLab remotes
  └── LLM API     — narration only (--narrate)
```

---

### 3.3 Data Flow: `fossil explain src/billing/legacy_processor.py`

1. CLI parses arguments; resolves `src/billing/legacy_processor.py` to absolute path.
2. Validates: file exists, path is inside a git repository, file is not binary/generated.
3. Cache store checks `(abs_path, git_HEAD_hash, repo_root)` → if cache hit, jump to step 13.
4. Analyzer registry maps `.py` extension → `PythonAnalyzer`.
5. `PythonAnalyzer` builds a symbol table: all exported names in the target file (classes, functions, module-level names).
6. `PythonAnalyzer` scans every other file in the repo: finds all `import`, `from ... import`, and string-based reference patterns matching the target file's symbols.
7. `PythonAnalyzer` detects dynamic patterns in the target file: `importlib`, `getattr`, `__import__`, `eval`, `exec`.
8. `GitMiner` runs `git log --follow --diff-filter=M -- <abs_path>` to retrieve the full commit history for the file.
9. `GitMiner` traverses commits newest-to-oldest, checking at each commit whether any other file in the repo imported or called this file. The first commit where references dropped to zero is the "death commit."
10. `CommitParser` extracts PR number from death commit message (patterns: `#NNN`, `PR NNN`, `pull request NNN`). If found and token is configured, calls GitHub/GitLab API for PR title and body.
11. `PatternDetector` scans current file content for deferred-deletion comments. For each pattern found, attempts to resolve the condition (PR number lookup, version tag check, date comparison).
12. `ConfidenceScorer` receives all signals from steps 6–11, computes weighted score, produces `ConfidenceResult` with label and per-signal breakdown.
13. (Optional) `LLMNarrator` receives `ForensicResult` as structured JSON, calls LLM with prompt template, returns narration string.
14. `CacheStore` writes `(abs_path, git_HEAD_hash, repo_root) → result_json`.
15. `OutputRenderer` renders Rich panel to stdout (or JSON if `--json`).
16. Exit 0.

---

### 3.4 CLI Command Interface Specification

> `fossil` is a pure CLI tool with no HTTP server. This section specifies the command interface contract in place of HTTP API endpoints.

---

#### `fossil explain <target>`

**Purpose:** Full forensic report for a single file or symbol.

**Arguments:**
- `<target>` — relative or absolute path to a file (e.g., `src/billing/processor.py`) OR a dotted symbol path (e.g., `src.billing.processor.LegacyProcessor`) [symbol-level analysis: Phase 3]

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--json` | bool | false | Output machine-readable JSON |
| `--narrate` | bool | false | Append LLM-generated natural language explanation |
| `--include-code` | bool | false | Send source code to LLM (requires --narrate; consent prompt shown) |
| `--no-cache` | bool | false | Skip cache read and write |
| `--no-color` | bool | false | Disable ANSI color output |
| `--depth` | int | 500 | Maximum commits to traverse in git history |
| `--remote` | enum | auto | Force remote type: `github`, `gitlab`, `none` |
| `--yolo` | bool | false | Generate deletion PR if confidence ≥ 90% |
| `--force-yolo` | bool | false | Generate deletion PR regardless of confidence (with warning) |

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Success — file is dead, report generated |
| 1 | Unexpected error |
| 2 | File not found |
| 3 | Not a git repository |
| 4 | File is NOT dead — actively used |
| 5 | Language not supported |

**JSON output shape:**
```json
{
  "fossil_version": "0.3.1",
  "target": "src/billing/legacy_processor.py",
  "abs_path": "/home/user/myrepo/src/billing/legacy_processor.py",
  "repo_root": "/home/user/myrepo",
  "language": "python",
  "dead": true,
  "dead_since": "2023-03-14T10:22:00Z",
  "last_live_commit": {
    "hash": "f8c2d41",
    "date": "2023-01-09T08:14:00Z",
    "message": "Add SCA handling for EU Payment Services Directive"
  },
  "death_commit": {
    "hash": "a3f9b21",
    "short_hash": "a3f9b21",
    "date": "2023-03-14T10:22:00Z",
    "message": "Migrate to Stripe v3 — replace legacy SCA handler (#441)",
    "author_name": "Sarah Chen",
    "author_email": "sarah@example.com",
    "pr_number": 441,
    "pr_title": "Migrate to Stripe v3 — replace legacy SCA handler",
    "pr_body_summary": "Replaces LegacyProcessor with StripeService.handleSCA() as part of Stripe API v3 migration.",
    "pr_url": "https://github.com/org/repo/pull/441"
  },
  "original_author": {
    "name": "Sarah Chen",
    "email": "sarah@example.com",
    "first_commit_date": "2022-06-12T09:00:00Z"
  },
  "inferred_intent": "Handled SCA (Strong Customer Authentication) for EU customers under PSD2.",
  "replacement": {
    "detected": true,
    "file": "payments/stripe.py",
    "line": 88,
    "symbol": "StripeService.handleSCA"
  },
  "temporary_hold": {
    "detected": true,
    "patterns": [
      {
        "text": "keeping this around until Q2 rollout completes",
        "line": 3,
        "condition": "Q2 rollout",
        "condition_type": "milestone",
        "condition_met": true,
        "condition_evidence": "PR #489 'Complete Q2 Stripe rollout' merged 2023-04-12"
      }
    ]
  },
  "static_analysis": {
    "call_sites": 0,
    "import_references": 0,
    "dynamic_references": 0,
    "reflection_patterns": [],
    "test_file_references": 0,
    "config_file_references": 0,
    "documentation_references": 0
  },
  "confidence": {
    "score": 91,
    "label": "High",
    "risk": "Low",
    "signals": [
      { "name": "zero_call_sites", "weight": 30, "applied": true },
      { "name": "no_dynamic_references", "weight": 20, "applied": true },
      { "name": "death_commit_found", "weight": 15, "applied": true },
      { "name": "temporary_hold_resolved", "weight": 10, "applied": true },
      { "name": "no_reflection_patterns", "weight": 10, "applied": true },
      { "name": "file_age_days_462", "weight": 6, "applied": true }
    ]
  },
  "suggested_action": "rm src/billing/legacy_processor.py",
  "yolo_command": "fossil explain src/billing/legacy_processor.py --yolo",
  "narration": null,
  "analysis_duration_ms": 1840,
  "cached": false
}
```

---

#### `fossil scan [directory]`

**Purpose:** Scan a directory for all dead files above a confidence threshold.

**Arguments:**
- `[directory]` — defaults to current working directory

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--threshold` | int | 70 | Only show files with confidence ≥ N% |
| `--language` | str | all | Comma-separated language filter: `py,js,ts,java,go` |
| `--exclude` | str | none | Glob patterns to exclude (e.g., `**/migrations/**`) |
| `--json` | bool | false | Machine-readable JSON output |
| `--output` | enum | table | Terminal format: `table`, `list`, `compact` |
| `--no-cache` | bool | false | Force fresh analysis |
| `--depth` | int | 500 | Max commits to traverse per file |

**Exit codes:** 0 = dead code found above threshold; 4 = no dead code found (useful for CI assertions).

---

#### `fossil clean [directory]`

**Purpose:** Batch explain all dead files above threshold; output a prioritized deletion backlog.

**Options:**

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--threshold` | int | 80 | Minimum confidence to include |
| `--dry-run` | bool | false | Show what would be done without doing it |
| `--yolo` | bool | false | Generate deletion PRs for all files above threshold |
| `--json` | bool | false | Machine-readable output |

---

#### `fossil config set <key> <value>`

**Purpose:** Set a configuration value in `~/.config/fossil/config.toml`.

**Keys:** `github_token`, `gitlab_token`, `llm_provider`, `llm_api_key`, `llm_model`, `default_depth`, `cache_ttl_hours`

**Behaviour:** Immediately validates tokens via a lightweight API call. Stores values with 0600 file permissions. Masks tokens in all display output (shows only last 4 characters).

---

#### `fossil config show`

**Purpose:** Display current configuration with masked sensitive values.

---

#### `fossil cache clear`

**Purpose:** Delete `.fossil/cache.db` in the current repository.

---

### 3.5 Local Cache Schema (SQLite)

**File location:** `.fossil/cache.db` (in repo root, gitignored)

**Table: `analysis_results`**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| `file_path` | TEXT | NOT NULL | Absolute path to analyzed file |
| `git_head_hash` | TEXT | NOT NULL | SHA of current HEAD at analysis time — invalidation key |
| `repo_root` | TEXT | NOT NULL | Absolute repo root path |
| `result_json` | TEXT | NOT NULL | Full serialized `ForensicResult` JSON |
| `created_at` | INTEGER | NOT NULL | Unix timestamp |
| `fossil_version` | TEXT | NOT NULL | Semantic version string |
| | | UNIQUE(file_path, git_head_hash, repo_root) | |

**Table: `pr_cache`**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| `remote_url` | TEXT | NOT NULL | Canonical remote URL |
| `pr_number` | INTEGER | NOT NULL | PR/MR number |
| `pr_title` | TEXT | | |
| `pr_body` | TEXT | | |
| `merged_at` | TEXT | | ISO8601 datetime or NULL |
| `cached_at` | INTEGER | NOT NULL | Unix timestamp |
| | | UNIQUE(remote_url, pr_number) | |

**Table: `scan_results`**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | |
| `repo_root` | TEXT | NOT NULL | |
| `scan_target` | TEXT | NOT NULL | Directory path scanned |
| `git_head_hash` | TEXT | NOT NULL | Invalidation key |
| `result_json` | TEXT | NOT NULL | Array of abbreviated ForensicResult objects |
| `created_at` | INTEGER | NOT NULL | Unix timestamp |
| | | UNIQUE(repo_root, scan_target, git_head_hash) | |

**Table: `schema_version`**

| Column | Type | Description |
|--------|------|-------------|
| `version` | INTEGER | Current schema version for migration support |

---

## 4. Terminal UX Specification

> `fossil` is a CLI tool. "UI" is the terminal. This section specifies terminal output design, formatting conventions, user flows, and accessibility behavior.

---

### 4.1 `fossil explain` — Primary Output

```
╭─ fossil ─────────────────────────────────────────────────────────────────────╮
│                                                                               │
│  FORENSIC REPORT  src/billing/legacy_processor.py                            │
│  Status  ● DEAD   Language  Python   Size  142 lines                         │
│                                                                               │
│  ┌ History ────────────────────────────────────────────────────────────────┐ │
│  │  Dead since    March 14, 2023 · 14 months ago                           │ │
│  │  Death commit  a3f9b21  "Migrate to Stripe v3 — replace legacy SCA..."  │ │
│  │  PR            #441 · Migrate to Stripe v3 — replace legacy SCA handler │ │
│  │  Original by   Sarah Chen · first committed June 12, 2022               │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌ Intent ─────────────────────────────────────────────────────────────────┐ │
│  │  Purpose     SCA authentication for EU customers (PSD2 compliance)       │ │
│  │  Replaced by payments/stripe.py:88 · StripeService.handleSCA()          │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌ Temporary Hold ─────────────────────────────────────────────────────────┐ │
│  │  Pattern   "keeping this around until Q2 rollout completes" (line 3)    │ │
│  │  Status    ✓ RESOLVED  —  PR #489 merged April 12, 2023                 │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌ Static Analysis ────────────────────────────────────────────────────────┐ │
│  │  Call sites         0     Dynamic imports  0                             │ │
│  │  Import refs        0     Reflection       None detected                 │ │
│  │  Test references    0     Config refs      0                             │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌ Confidence ─────────────────────────────────────────────────────────────┐ │
│  │   91%  ██████████████████░░  HIGH CONFIDENCE · LOW RISK                 │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  Suggested   rm src/billing/legacy_processor.py                               │
│  Auto-PR     fossil explain src/billing/legacy_processor.py --yolo           │
│                                                                               │
╰───────────────────────────────────────────────────────────────────────────────╯
```

---

### 4.2 `fossil scan` — Table Output

```
$ fossil scan ./src  (143 files · 3 languages)  ━━━━━━━━━━━━━━━━━━━━━━  100%

  File                                          Language  Dead Since    Confidence
  ─────────────────────────────────────────────────────────────────────────────────
  src/billing/legacy_processor.py               Python    Mar 2023          91%
  src/auth/old_oauth_handler.py                 Python    Nov 2022          87%
  src/utils/deprecated_formatter.py             Python    Jan 2024          74%
  src/api/v1/legacy_endpoints.py                Python    Jun 2022          68%

  4 dead files found above 70% threshold.
  Estimated removable: ~2,400 LOC across 4 files.

  Run fossil explain <file> for full forensic report.
  Run fossil clean --threshold 80 to see a deletion backlog.
```

---

### 4.3 Color Scheme

| Element | Color |
|---------|-------|
| "DEAD" status | Bold Red |
| High confidence (≥85%) | Bold Green |
| Medium confidence (60–84%) | Yellow |
| Low confidence (<60%) | Red |
| Commit hashes | Cyan |
| File paths | Cyan |
| Section headers | Bold White |
| Secondary info (dates, emails) | Dim White |
| Progress bars | Blue fill |
| `✓` resolved conditions | Green |
| `✗` unresolved conditions | Red |
| `⚠` warnings | Yellow |

**Accessibility rule:** Every piece of information conveyed by color must also be conveyed in text. "HIGH CONFIDENCE" is always printed alongside the green color — the color is never the sole signal.

---

### 4.4 User Flows

**Core flow — single file forensics:**
1. Developer notices a suspicious file in their editor.
2. Opens terminal, types `fossil explain src/billing/legacy_processor.py`.
3. Reads the forensic panel: confirms dead since March 2023, replacement found, temporary hold resolved.
4. Confidence is 91%. Developer runs `fossil explain ... --yolo`.
5. fossil creates branch `fossil/remove-legacy-processor`, commits deletion, pushes, opens PR.
6. Developer opens PR link, adds reviewers, merges.

**Discovery flow — codebase audit:**
1. Tech lead runs `fossil scan ./src --threshold 80`.
2. Reviews table of dead files sorted by confidence.
3. Runs `fossil explain` on the top 3 for full forensic context.
4. Runs `fossil clean --threshold 85 --dry-run` to preview batch cleanup plan.
5. Runs `fossil clean --threshold 85 --yolo` to generate PRs for all high-confidence candidates.

**CI flow — prevent dead code accumulation:**
1. CI runs `fossil scan . --threshold 90 --json > dead_report.json`.
2. Exit code 0 = dead code exists above 90% → CI step fails with annotation.
3. Exit code 4 = no dead code above 90% → CI step passes.
4. Developer sees failure, checks report, resolves.

---

### 4.5 Plain / Accessibility Mode

- `--plain` → output plain ASCII text with no Rich formatting, no panels, no progress bars. All information is retained; only visual decorations removed.
- `--no-color` → disable ANSI color codes; respect `NO_COLOR` environment variable (https://no-color.org/).
- `fossil --help` provides full command documentation inline; no man page required.
- Shell completions (bash, zsh, fish) auto-generated by Typer.

---

## 5. Authentication & Authorization

> `fossil` is a local CLI tool with no user login system. "Authentication" refers to API credential management for external services.

### 5.1 Credential Types

| Credential | Service | Required For | Storage |
|------------|---------|--------------|---------|
| `GITHUB_TOKEN` | GitHub | PR lookup, `--yolo` PR creation | `~/.config/fossil/config.toml` |
| `GITLAB_TOKEN` | GitLab | PR lookup, `--yolo` PR creation | `~/.config/fossil/config.toml` |
| `FOSSIL_LLM_API_KEY` | LLM provider | `--narrate` mode | `~/.config/fossil/config.toml` |

### 5.2 Credential Storage Rules

- Config file stored at `~/.config/fossil/config.toml` with Unix permissions `0600` (owner read/write only).
- On write, fossil explicitly calls `os.chmod(config_path, 0o600)`.
- Credentials are never included in `--json` output, log output, error messages, or LLM prompts.
- `fossil config show` masks tokens: `ghp_...xxxx` (last 4 characters visible only).
- Environment variables (`GITHUB_TOKEN`, `FOSSIL_LLM_API_KEY`) override config file values and are never persisted to disk.

### 5.3 Token Scopes Required

**GitHub Token:**
- `repo` scope for private repos (read commits + create PRs)
- `public_repo` scope for public repos only

**GitLab Token:**
- `api` scope (read/write access to GitLab API)

### 5.4 Token Validation

When `fossil config set github_token <value>` is run:
1. Makes `GET /user` to `api.github.com` with the token.
2. On 200: `✓ GitHub token validated. Authenticated as: @username`
3. On 401: `✗ Token invalid: 401 Unauthorized. Check your token.`
4. On 403: `✗ Token valid but insufficient scopes. Required: repo. Current scopes: <list>`
5. On network error: `⚠ Could not validate token (network error). Token saved but unverified.`

### 5.5 Offline Mode

All features except PR creation (`--yolo`) and LLM narration (`--narrate`) work with zero network access. fossil never makes network calls for core analysis.

---

## 6. Non-Functional Requirements

### 6.1 Performance Targets

| Operation | Target | Hard Limit |
|-----------|--------|------------|
| `fossil explain` (cache hit) | < 100ms | 500ms |
| `fossil explain` (single file, <10k commits) | < 3 seconds | 10 seconds |
| `fossil explain` (single file, 50k commits, `--depth 500`) | < 5 seconds | 15 seconds |
| `fossil scan` (1k files, Python only) | < 10 seconds | 30 seconds |
| `fossil scan` (50k files, all languages) | < 5 minutes | 10 minutes |
| Static analysis per file | < 200ms | 1 second |
| Git log traversal per 500 commits | < 1 second | 3 seconds |
| GitHub API PR lookup | < 2 seconds | 5 seconds (timeout) |
| LLM narration | < 10 seconds | 30 seconds (timeout) |

**Performance implementation notes:**
- `fossil scan` must stream results as they are found, not buffer everything into memory before displaying.
- Git log traversal must use GitPython's iterator API, not load full history into memory.
- Tree-sitter parsing must reuse grammar instances (no per-file grammar reload).
- For large repos, analysis must process files in parallel using `concurrent.futures.ThreadPoolExecutor` with a default of `min(32, os.cpu_count() + 4)` workers.

### 6.2 Security Requirements

- **No shell injection:** All git operations use GitPython library calls. No `subprocess.run("git ...")` string interpolation with user-provided paths.
- **Path traversal prevention:** All user-provided paths are resolved via `pathlib.Path.resolve()` and validated to be within the git repository root before any operation.
- **Credential safety:** API keys never appear in exceptions, log output, debug output, or JSON responses. `repr()` of config objects must mask token fields.
- **LLM data minimization:** By default, only structured metadata (dates, commit hashes, inferred strings) is sent to LLM API — never raw source code. `--include-code` requires an explicit interactive consent prompt: `This will send source code to <provider>. Continue? [y/N]`
- **Cache integrity:** SQLite cache is local-only. No integrity verification is required, but corruption is detected via try/except on parse and handled by cache rebuild.
- **No telemetry:** fossil makes zero outbound network connections beyond the three explicit external services (GitHub API, GitLab API, LLM API). No analytics, no error reporting, no update checks by default.
- **Input validation:** All CLI arguments are validated by Typer's type system. File paths, integer flags, and enum values are rejected at the CLI layer before reaching core logic.

### 6.3 Scalability

fossil is a single-machine CLI tool. "Scalability" means:
- Handling monorepos with 500k+ files without OOM: achieved via streaming `scan`, per-file analysis without loading all files, and LRU cache with size cap.
- Handling repos with 100k+ commits without hanging: achieved via `--depth` limit (default 500), traversal timeout, and early termination when death commit is found.
- Cache size management: auto-prune entries older than `cache_ttl_hours` when cache exceeds 100MB. If a single analysis result exceeds 5MB, it is not cached (edge case for deeply analyzed files).

### 6.4 Accessibility

- **Color independence:** All information conveyed by color is also conveyed by text labels.
- **`--no-color` flag:** Fully disables ANSI codes. Also respects `NO_COLOR` environment variable.
- **`--plain` flag:** Outputs plain text without Rich formatting, suitable for screen readers and piping.
- **Screen reader compatibility:** `--plain --no-color` output is a structured, consistently formatted text report with no visual-only characters.
- **Shell completions:** Tab completion for file paths, flags, and enum values reduces typing burden.

---

## 7. File & Folder Structure

```
fossil/
│
├── src/
│   └── fossil/
│       ├── __init__.py              # Package version (__version__ = "0.1.0")
│       ├── cli.py                   # Root Typer app; global flags (--no-color,
│       │                            # --plain, --version); registers subcommands
│       │
│       ├── commands/                # One module per top-level command
│       │   ├── __init__.py
│       │   ├── explain.py           # fossil explain — orchestrates full pipeline
│       │   ├── scan.py              # fossil scan — directory traversal + batch explain
│       │   ├── clean.py             # fossil clean — batch explain + optional PR gen
│       │   └── config.py            # fossil config set/show/reset
│       │
│       ├── analyzers/               # Language-specific static analysis
│       │   ├── __init__.py
│       │   ├── base.py              # Abstract LanguageAnalyzer: analyze(file, repo) → StaticResult
│       │   ├── registry.py          # Maps file extension → analyzer class; detects language
│       │   ├── python.py            # Python: ast module for deep analysis + tree-sitter for refs
│       │   ├── javascript.py        # JS/TS: tree-sitter-javascript / tree-sitter-typescript
│       │   ├── java.py              # Java: tree-sitter-java
│       │   ├── go.py                # Go: tree-sitter-go
│       │   └── generic.py           # Fallback: text-search for filename/symbol references
│       │
│       ├── git/                     # All git interaction
│       │   ├── __init__.py
│       │   ├── repo.py              # Detect repo root; validate git repo; detect remote type
│       │   ├── miner.py             # git log traversal; death commit algorithm; commit history
│       │   ├── blame.py             # git blame for original authorship attribution
│       │   └── pr_parser.py         # Extract PR# from commit messages; fetch PR via API
│       │
│       ├── patterns/                # Comment pattern detection
│       │   ├── __init__.py
│       │   └── detector.py          # Regex + AST detection of deferred-deletion patterns;
│       │                            # condition verification logic (PR merged?, date passed?)
│       │
│       ├── scoring/                 # Confidence computation
│       │   ├── __init__.py
│       │   └── confidence.py        # Aggregates StaticResult + GitResult + PatternResult
│       │                            # → ConfidenceResult (score, label, risk, signal breakdown)
│       │
│       ├── narration/               # Optional LLM integration
│       │   ├── __init__.py
│       │   └── llm.py               # litellm wrapper; prompt templates; response parsing;
│       │                            # provider configuration; consent prompt for --include-code
│       │
│       ├── output/                  # Rendering layer
│       │   ├── __init__.py
│       │   ├── terminal.py          # Rich panels, tables, progress bars, color theme
│       │   ├── json_renderer.py     # ForensicResult → JSON string
│       │   └── themes.py            # Color constants; --no-color toggle
│       │
│       ├── pr/                      # --yolo PR generation
│       │   ├── __init__.py
│       │   └── generator.py         # Branch creation; file deletion commit; push; PR creation
│       │                            # via PyGithub / python-gitlab
│       │
│       ├── cache/                   # Local SQLite result cache
│       │   ├── __init__.py
│       │   └── store.py             # CRUD; invalidation by git HEAD; size management; pruning
│       │
│       ├── config/                  # Configuration management
│       │   ├── __init__.py
│       │   └── manager.py           # Read ~/.config/fossil/config.toml and .fossil.toml;
│       │                            # env var override; validation; masked display
│       │
│       └── models.py                # Pydantic v2 models:
│                                    #   ForensicResult, DeathCommit, TemporaryHold,
│                                    #   StaticAnalysisResult, ConfidenceResult,
│                                    #   ScanResult, ReplacementInfo
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # pytest fixtures: build_git_repo() helper that creates
│   │                                # ephemeral git repos with controlled commit history
│   ├── fixtures/
│   │   ├── python_dead_class/       # Fixture: Python repo where a class becomes dead in commit 3
│   │   ├── js_dead_module/          # Fixture: JS repo with dead module
│   │   ├── temp_hold_resolved/      # Fixture: "TODO: remove after X" where X was completed
│   │   ├── dynamic_import/          # Fixture: file that appears dead but has importlib usage
│   │   └── shallow_clone/           # Fixture: simulates shallow git clone behavior
│   ├── test_analyzers/
│   │   ├── test_python.py
│   │   └── test_javascript.py
│   ├── test_git/
│   │   ├── test_miner.py
│   │   └── test_pr_parser.py
│   ├── test_patterns/
│   │   └── test_detector.py
│   ├── test_scoring/
│   │   └── test_confidence.py
│   └── test_commands/
│       ├── test_explain.py          # End-to-end tests using fixture repos
│       └── test_scan.py
│
├── docs/
│   ├── ARCHITECTURE.md              # Mirrors §3 of this document
│   ├── CONTRIBUTING.md              # Dev setup, test conventions, PR guidelines
│   └── LANGUAGE_SUPPORT.md         # Per-language analyzer capabilities and limitations
│
├── pyproject.toml                   # Build system (hatchling), dependencies, entry point,
│                                    # ruff config, mypy config, pytest config
├── README.md                        # Installation, quickstart, command reference
├── CHANGELOG.md
└── .github/
    └── workflows/
        ├── ci.yml                   # On PR: pytest, ruff check, mypy, coverage
        └── release.yml              # On tag push: build wheel, publish to PyPI
```

---

## 8. Environment & Configuration

### 8.1 Environment Variables

| Variable | Purpose | Example Value | Required |
|----------|---------|---------------|----------|
| `GITHUB_TOKEN` | GitHub API auth for PR lookup and `--yolo` | `ghp_xxxxxxxxxxxxxxxxxxxx` | No (optional features) |
| `GITLAB_TOKEN` | GitLab API auth for PR lookup and `--yolo` | `glpat-xxxxxxxxxxxxxxxxxxxx` | No (optional features) |
| `FOSSIL_LLM_PROVIDER` | LLM provider for `--narrate` | `openai` / `anthropic` / `ollama` | No (narration only) |
| `FOSSIL_LLM_API_KEY` | API key for LLM narration | `sk-xxxxxxxxxxxxxxxxxxxx` | No (narration only) |
| `FOSSIL_LLM_MODEL` | Specific model for narration | `gpt-4o-mini` / `claude-haiku-4-5-20251001` | No |
| `FOSSIL_CACHE_DIR` | Override cache directory location | `/tmp/fossil-cache` | No |
| `FOSSIL_LOG_LEVEL` | Logging verbosity | `DEBUG` / `INFO` / `WARNING` / `ERROR` | No (default: `WARNING`) |
| `NO_COLOR` | Disable all ANSI color output (no-color.org standard) | `1` | No |
| `FOSSIL_NO_COLOR` | fossil-specific color disable | `1` | No |
| `FOSSIL_DEFAULT_DEPTH` | Default git traversal depth | `1000` | No (default: `500`) |

> All environment variables override their corresponding config file values. No restart required.

---

### 8.2 User Config File: `~/.config/fossil/config.toml`

```toml
[auth]
github_token = ""       # Set via: fossil config set github_token <token>
gitlab_token = ""
llm_api_key  = ""       # Never printed in full; masked in fossil config show

[llm]
provider      = "openai"       # openai | anthropic | ollama | azure
model         = "gpt-4o-mini"  # Any model supported by litellm
base_url      = ""             # For ollama or self-hosted: http://localhost:11434
include_code  = false          # If true, source code is sent to LLM in --narrate mode

[analysis]
default_depth    = 500         # Max git commits to traverse
cache_ttl_hours  = 24          # Cache entries older than this are pruned
exclude_patterns = [           # Global exclusions (gitignore-style globs)
  "**/node_modules/**",
  "**/dist/**",
  "**/__pycache__/**",
  "**/.venv/**"
]

[output]
color = true          # Disable with: fossil config set output.color false
theme = "default"     # Currently only "default" supported; future: "minimal", "dark"
```

---

### 8.3 Project Config File: `.fossil.toml` (in repo root, committed)

Allows teams to share project-specific fossil configuration without requiring each developer to configure individually.

```toml
[analysis]
languages        = ["py", "js", "ts"]     # Restrict scan to these languages
exclude_patterns = ["**/migrations/**", "**/generated/**", "**/*.pb.py"]

[thresholds]
minimum_confidence      = 70   # fossil scan default threshold for this project
yolo_minimum_confidence = 90   # Minimum confidence allowed for --yolo in this repo

[pr]
base_branch     = "main"       # Branch to target for --yolo PRs
pr_labels       = ["dead-code-cleanup", "automated"]
pr_reviewers    = []           # Optional: list of GitHub usernames to auto-assign
```

---

### 8.4 External Services

| Service | URL | Used For | Required |
|---------|-----|----------|----------|
| GitHub API | `https://api.github.com` | Fetch PR title/body from PR numbers; create deletion PRs via `--yolo` | No |
| GitLab API | `https://gitlab.com/api/v4` (or self-hosted) | Same as GitHub, for GitLab remotes | No |
| LLM Provider | Provider-specific (OpenAI, Anthropic, Ollama, etc.) | Natural language narration via `--narrate` | No |

**All external services are optional.** fossil's core forensic analysis (static analysis, git mining, pattern detection, confidence scoring, terminal output) works with zero network access.

---

## 9. Development Phases & Milestones

---

### Phase 1: MVP — Python Forensics (Complexity: **Medium**)

**Goal:** A working, installable `fossil explain` for Python repositories.

**Deliverables:**

- `fossil explain <python_file>` end-to-end: static analysis → git mining → confidence scoring → Rich terminal output.
- `PythonAnalyzer`: uses Python's `ast` module to find all exported symbols in the target file, then scans all other `.py` files for imports and attribute references to those symbols.
- `GitMiner`: `git log --follow` traversal to find death commit. Basic commit message parsing for PR number extraction (regex: `#\d+`, `PR \d+`).
- `ConfidenceScorer`: 5 signals: zero call sites, death commit found, no dynamic imports (`importlib`, `__import__`), file age, PR reference found.
- Rich terminal output: the panel layout described in §4.1.
- `fossil config set github_token` with validation.
- Config file read/write with 0600 permissions.
- SQLite cache: explain results cached by `(file_path, git_HEAD)`.
- Exit codes: 0, 2, 3, 4 (file is live).
- `--json` flag for `fossil explain`.
- `--no-color` and `--plain` flags.
- pytest suite: 3 fixture repos covering happy path, no-history case, and live-file case.
- `pyproject.toml` with `fossil` entry point; `pip install fossil-cli` works.

**Out of scope for Phase 1:** Multi-language support, scan command, pattern detection, GitHub API PR fetching, `--yolo`, LLM narration.

---

### Phase 2: Multi-Language + Scan (Complexity: **Medium-High**)

**Goal:** Expand language support and add directory scanning.

**Deliverables:**

- `fossil scan [directory]` command with table output, threshold filtering, language filter.
- tree-sitter integration: `JavaScriptAnalyzer`, `TypeScriptAnalyzer`, `JavaAnalyzer`, `GoAnalyzer`.
- `GenericAnalyzer` fallback: text-search for filename/symbol references for unsupported languages.
- `PatternDetector`: detects "TODO: remove", "keep for now", "DEPRECATED", and similar patterns. Condition verification: PR number → check merge status (requires GitHub token), date → compare to today, version → check git tags.
- Expanded `ConfidenceScorer`: all signals from §2.6 including pattern detection signals.
- `fossil scan --json` machine-readable output.
- `--threshold`, `--language`, `--exclude` flags for `fossil scan`.
- Progress bar for scan (Rich `Progress`).
- `.fossil.toml` project-level config support.
- Parallel file processing for scan via `ThreadPoolExecutor`.
- Exit code 4 for "no dead code found" (CI use case).
- Scan result caching.
- Expanded test suite: 8 fixture repos across 4 languages.

---

### Phase 3: GitHub/GitLab Integration + PR Generation (Complexity: **High**)

**Goal:** Connect to remote APIs and enable automated deletion PR creation.

**Deliverables:**

- GitHub API integration: fetch PR title, body, merge date, review status for referenced PR numbers.
- GitLab API integration: same for GitLab remotes (gitlab.com and self-hosted).
- Auto-detection of remote type from `git remote get-url origin`.
- `--yolo` flag for `fossil explain`: creates branch, stages deletion, commits, pushes, opens PR via API.
- `--force-yolo` flag: overrides confidence threshold guard (shows explicit warning).
- `fossil clean [directory]` command: batch explain all dead files above threshold, output ranked backlog, optional `--yolo` for batch PR generation.
- `fossil config set` token validation with scope checking.
- PR branch naming: `fossil/remove-<filename-slug>-<short-hash>`.
- PR template: auto-populated body with forensic summary, confidence score, and death commit reference.
- Duplicate branch detection and `-2`, `-3` suffixing.
- Test suite additions: mock GitHub/GitLab API responses; test `--yolo` workflow end-to-end with mocked API.

---

### Phase 4: LLM Narration + Polish (Complexity: **Medium**)

**Goal:** Add natural language narration and release-quality polish.

**Deliverables:**

- `--narrate` flag: sends structured `ForensicResult` to LLM, appends human-readable explanation to output.
- litellm integration: supports OpenAI, Anthropic, Ollama, Azure OpenAI. Model configurable via `fossil config set llm_model`.
- Offline narration via Ollama (model: `llama3` or `mistral`): works with no external API key.
- `--include-code` flag with interactive consent prompt.
- LLM timeout handling: 30 seconds, graceful fallback to structured output.
- LLM prompt templates stored as plain-text files in `src/fossil/narration/prompts/`.
- Shell completion generation: `fossil --install-completion` for bash, zsh, fish (Typer built-in).
- `fossil cache clear` and `fossil cache stats` commands.
- Homebrew formula submission to a public tap.
- Comprehensive README with quickstart, command reference, FAQ, and CI integration guide.
- CHANGELOG.md and semantic versioning from Phase 1 onward.
- (Stretch) VS Code extension: reads `fossil explain --json` output and shows inline "Fossil: DEAD 91%" decoration in the file explorer.

---

## 10. Glossary

**Call site:** A location in the codebase where a function, class, or module is explicitly referenced — via an import statement, direct function call, attribute access, or instantiation. Zero call sites is a primary indicator of dead code.

**Confidence score:** A 0–100 integer representing fossil's certainty that a given file or symbol is safe to delete. Computed by aggregating weighted signals from static analysis, git history, and pattern detection.

**Dead code:** Source code that is never executed in any foreseeable runtime path — not imported, not called, not referenced — and which has no intended future use. Distinguished from "commented-out" code and from code that is unreachable due to branching logic.

**Death commit:** The specific git commit at which a file transitioned from being actively referenced to having zero references in the rest of the codebase. The commit that "killed" the code.

**Deferred deletion:** A pattern where a developer intentionally keeps dead code temporarily, intending to remove it after some condition is met (a migration completes, a rollout finishes, a certain date passes). Detected via comment patterns like "TODO: remove after X".

**Dynamic reference:** A code pattern where a module or symbol is loaded or accessed via runtime string construction rather than a static import — e.g., `importlib.import_module("module_name")`, `getattr(obj, method_name)`. Dynamic references cannot be detected by static analysis alone and reduce confidence in deletion safety.

**Forensic analysis:** fossil's core approach: treating dead code not as a static state but as the product of a history — understanding *when*, *how*, and *why* code died, not just *that* it is dead.

**git HEAD:** The SHA-1 hash of the current commit in a git repository. Used by fossil as a cache invalidation key: if HEAD changes, all cached analysis results are stale.

**LLM narration:** An optional feature where fossil sends structured forensic metadata to a large language model to generate a human-readable paragraph summarizing the findings. Source code is not sent unless `--include-code` is explicitly used.

**Reflection pattern:** A programming technique where code references other code indirectly via string names resolved at runtime — e.g., Python's `getattr`, `hasattr`, `vars()`, or JavaScript's `obj[methodName]`. Reflection patterns reduce confidence because static analysis cannot prove the absence of runtime references.

**Replacement:** When a piece of dead code was deliberately superseded by a newer implementation, fossil attempts to identify the specific file, line, and symbol that replaced it — providing context for why the dead code can be safely removed.

**Risk label:** A qualitative label (Low / Medium / High) assigned alongside the confidence score to describe the consequence of an incorrect deletion decision. Low risk = easy to revert; High risk = deletion could have non-obvious consequences.

**Shallow clone:** A git repository cloned with limited history depth (e.g., `git clone --depth 50`). Common in CI environments. fossil detects shallow clones and warns that git history analysis may be incomplete.

**Static analysis:** The examination of source code without executing it — parsing the code's structure (AST) to find imports, references, and call sites. fossil uses static analysis as the first signal of deadness.

**Temporary hold pattern:** A comment within dead code indicating the developer intentionally deferred deletion pending some condition. See "deferred deletion."

**tree-sitter:** An incremental parsing library that generates concrete syntax trees for 50+ programming languages. fossil uses tree-sitter grammars for language-agnostic reference detection across Python, JavaScript, TypeScript, Java, and Go.

**`--yolo`:** fossil's flag for automated deletion PR generation. When passed, fossil creates a git branch, deletes the target file, commits, pushes, and opens a pull request via the GitHub or GitLab API. Requires a configured API token and a confidence score ≥ 90%.

---

## ✅ Ready to Build — Pre-Coding Decision Checklist

Before writing the first line of code, the following decisions must be made:

- [ ] **Package name on PyPI:** `fossil-cli` is the suggested name (since `fossil` is taken by a version control system). Confirm availability and choose final name. This affects the entry point in `pyproject.toml` and all installation documentation.

- [ ] **Symbol-level vs. file-level analysis in Phase 1:** This spec primarily describes file-level analysis (the whole file is dead). Decide whether Phase 1 includes symbol-level analysis (`fossil explain src/module.py::MyClass`). Symbol-level is significantly more complex. Recommendation: file-level only for Phase 1.

- [ ] **Concurrent.futures vs asyncio for parallel scan:** The scan command needs parallelism. `ThreadPoolExecutor` is simpler and works well for I/O-bound git operations. `asyncio` would require async-compatible git bindings. Decision: `ThreadPoolExecutor` is recommended; document this choice.

- [ ] **Minimum Python version:** This spec assumes 3.11+ for `tomllib`. If 3.9/3.10 support is needed, add `tomli` as a dependency for those versions. Confirm minimum supported version.

- [ ] **tree-sitter grammar bundling strategy:** tree-sitter language grammars must be compiled or downloaded. Decide: (a) bundle pre-compiled grammars in the wheel, (b) compile at first run, or (c) require users to install language packages separately (e.g., `pip install fossil-cli[javascript]`). Option (c) is recommended for distribution size.

- [ ] **GitHub token scope strategy:** `repo` scope gives broad access. For read-only PR lookup (non-`--yolo` features), only `public_repo` or a fine-grained token with `pull_requests: read` is needed. Decide whether to require a single broad token or guide users through minimal-scope tokens for each feature tier.

- [ ] **LLM prompt template content:** The narration prompt templates in `src/fossil/narration/prompts/` must be authored. The quality of the narration feature depends entirely on these prompts. Decide who authors and tests them, and whether they are user-overridable.

- [ ] **Cache location:** This spec uses `.fossil/cache.db` in the repo root. This must be added to `.gitignore`. Alternatively, cache in `~/.cache/fossil/<repo-hash>.db` (no gitignore needed, but cache is lost if repo is moved). Choose one location.

- [ ] **Confidence threshold defaults:** The spec suggests 70% for `fossil scan`, 90% for `--yolo`. These are initial values — they should be validated against real codebases before release to ensure they are calibrated correctly. Plan to run fossil against 3–5 real open source repos before finalizing defaults.

- [ ] **GitLab self-hosted URL handling:** GitLab instances can be at any URL. Decide how fossil detects and handles self-hosted GitLab (parse `origin` URL, allow config override `fossil config set gitlab_url https://gitlab.mycompany.com`).

- [ ] **Handling of monorepos:** In a monorepo with 20 services, "is this file dead?" depends on which service's call graph you analyze. Decide whether fossil scans the entire repo root or respects a user-specified scope. The `--scope` flag concept should be designed before implementation.

- [ ] **`--yolo` PR review and merge strategy:** Should generated PRs include a standard body template? Should they auto-request reviewers? Should a minimum CI check be required before merge? These are repository policy decisions that affect the `pr/generator.py` implementation.

---

## Implementation Report — 2026-06-19

The first runnable implementation has been built in `/home/iamvvek/Dev/fossil` as `fossil-cli` version `0.1.0`.

### Decisions Closed

- [x] **Package name on PyPI:** Use `fossil-cli`; expose the executable as `fossil`.
- [x] **Symbol-level vs. file-level analysis in Phase 1:** File-level only. Symbol-level analysis remains a later feature because it changes the reference model and deletion semantics.
- [x] **Concurrent.futures vs asyncio for parallel scan:** `ThreadPoolExecutor` remains the intended design for large scans. The `0.1.0` implementation is serial until profiling on real repositories proves the right concurrency boundary.
- [x] **Minimum Python version:** Python 3.11+.
- [x] **tree-sitter grammar bundling strategy:** Optional extras later. The first release uses Python `ast` plus conservative text fallback so the core runs offline without compiled grammar dependencies.
- [x] **GitHub token scope strategy:** Token storage and masking are implemented. Network validation and PR creation are deliberately gated until the GitHub/GitLab API modules are implemented.
- [x] **Cache location:** `.fossil/cache.db` in the repository root; scaffold includes `.fossil/` in `.gitignore`.
- [x] **Confidence threshold defaults:** `scan` defaults to 70; `--yolo` remains blocked below 90.
- [x] **Handling of monorepos:** Current behavior scans the selected directory but evaluates references at repository scope. A future `--scope` flag should narrow reference analysis when needed.

### Shipped in 0.1.0

- Installable Python package with `fossil` console entry point.
- `fossil explain <file>` with JSON/plain output, cache support, exit codes, symlink/gitignored warnings, and untracked-file handling.
- Python static analyzer using `ast` for imports, exported symbols, calls, dynamic imports, and reflection risk.
- Conservative fallback analysis for JavaScript, TypeScript, Java, Go, docs, config files, and unknown files.
- Git history mining for tracked status, original author, last modification, shallow clone warning, likely death commit, PR-number extraction, and history-depth warning.
- Temporary hold detection for `TODO: remove after`, `FIXME: delete when`, `keep for now`, `temporary`, `DEPRECATED`, and `will be removed in`.
- Condition verification for dates, git tags/versions, and locally discoverable PR references.
- Confidence score with the documented weighted signals and risk labels.
- `fossil scan [directory]` with threshold filtering, language filtering, exclusion globs, JSON output, and exit code 4 when no candidates are found.
- `fossil clean [directory]` with prioritized deletion backlog output, dry-run support, JSON output, and guarded `--yolo` handling.
- `fossil cache clear`, `fossil config set`, and `fossil config show` with masked sensitive values and `0600` config permissions.
- SQLite cache schema for analysis and scan result storage.
- Documentation: README, architecture, language support, contributing guide, changelog.
- Tests: temporary real-git repositories covering dead-file, live-file, untracked-file, scan, and date-condition behavior.

### Explicitly Gated, Not Silently Faked

- `--narrate` returns a clear setup/integration error instead of pretending to call an LLM.
- `--yolo` enforces confidence gating and then returns a clear GitHub/GitLab integration error without changing files.
- Rich/Typer/GitPython/tree-sitter are documented as optional/future integration layers because they are not installed in the current environment and the first release must run offline.

### Verification

`env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -p no:cacheprovider` passes in `/home/iamvvek/Dev/fossil`: 5 tests passed.

`env PYTHONPATH=src python3 -m fossil.cli --help` passes in `/home/iamvvek/Dev/fossil`.
