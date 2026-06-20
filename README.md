<p align="center">
  <img src="docs/banner.svg" alt="fossil — dead code forensics" width="600">
</p>

<p align="center">
  <strong>Find dead code. Understand why it died. Safely delete it.</strong>
</p>

<p align="center">
  <a href="https://github.com/iamvvek/fossil/actions/workflows/ci.yml"><img src="https://github.com/iamvvek/fossil/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/fossil-code/"><img src="https://img.shields.io/pypi/v/fossil-code?color=%2334D058&label=pypi" alt="PyPI"></a>
  <a href="https://pypi.org/project/fossil-code/"><img src="https://img.shields.io/pypi/pyversions/fossil-code" alt="Python"></a>
  <a href="https://github.com/iamvvek/fossil/blob/main/LICENSE"><img src="https://img.shields.io/github/license/iamvvek/fossil?color=blue" alt="License"></a>
  <a href="https://github.com/iamvvek/fossil/issues"><img src="https://img.shields.io/github/issues/iamvvek/fossil" alt="Issues"></a>
</p>

---

`fossil` is a command-line forensics tool that goes beyond detecting dead code to explaining its *history* — **when** it died, **what** killed it, **who** wrote it, **why** it existed, and whether it is genuinely **safe to delete**.

It combines static analysis, git history mining, and pattern detection into a single terminal command that answers in under 3 seconds.

## Why fossil?

Every mature codebase accumulates dead code. Existing tools tell you **what** is dead. None of them tell you **why**.

| Question | Other Tools | fossil |
|----------|-------------|--------|
| Is this file imported anywhere? | ✅ | ✅ |
| When did it become dead? | ❌ | ✅ — exact death commit with date |
| What PR replaced it? | ❌ | ✅ — PR number, title, author |
| Who wrote it originally? | ❌ | ✅ — original author from git blame |
| Is there a "keep for now" comment? | ❌ | ✅ — detects and verifies the condition |
| Is it safe to delete? | ❌ | ✅ — 0–100% confidence score |
| Can it auto-delete for me? | ❌ | ✅ — `--yolo` creates a PR |

## Installation

```bash
pip install fossil-code
```

> Requires **Python 3.11+** and **git**.

## Quick Start

```bash
# Full forensic report for one file
fossil explain src/billing/legacy_processor.py

# Scan an entire directory
fossil scan ./src

# Machine-readable JSON output
fossil explain src/billing/legacy_processor.py --json

# Prioritized deletion backlog
fossil clean ./src --threshold 85

# Plain text mode (for piping / CI)
fossil explain src/billing/legacy_processor.py --plain
```

## Example Output

```
╭─────────────────────────────────── fossil ───────────────────────────────────╮
│                                                                              │
│    FORENSIC REPORT  src/billing/legacy_processor.py                          │
│    Status  ● DEAD   Language  Python                                         │
│  ╭─────────────────────────────── History ────────────────────────────────╮  │
│  │  Dead since        2023-03-14                                          │  │
│  │  Death commit      a3f9b21  "Migrate to Stripe v3 — replace legacy     │  │
│  │                    SCA handler (#441)"                                 │  │
│  │  PR                #441 · Migrate to Stripe v3 — replace legacy SCA    │  │
│  │                    handler (#441)                                      │  │
│  │  Original by       Sarah Chen · first committed 2022-06-12             │  │
│  ╰────────────────────────────────────────────────────────────────────────╯  │
│  ╭──────────────────────────── Temporary Hold ────────────────────────────╮  │
│  │   Pattern  "keeping this around until Q2 rollout completes" (line 3)   │  │
│  │   Status   ✓ RESOLVED  —  PR #489 merged April 12, 2023                │  │
│  ╰────────────────────────────────────────────────────────────────────────╯  │
│  ╭─────────────────────────── Static Analysis ────────────────────────────╮  │
│  │   Call sites          0        Dynamic imports     0                   │  │
│  │   Import refs         0        Reflection          None detected       │  │
│  │   Test references     0        Config refs         0                   │  │
│  ╰────────────────────────────────────────────────────────────────────────╯  │
│  ╭────────────────────────────── Confidence ──────────────────────────────╮  │
│  │    91%  ██████████████████░░  HIGH CONFIDENCE · LOW RISK               │  │
│  ╰────────────────────────────────────────────────────────────────────────╯  │
│    Suggested   rm src/billing/legacy_processor.py                            │
│    Auto-PR     fossil explain src/billing/legacy_processor.py --yolo         │
│    Analysis duration: 1840ms                                                 │
│                                                                              │
╰──────────────────────────────────────────────────────────────────────────────╯
```

## How It Works

For every file analyzed, `fossil` runs five stages in under 3 seconds:

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Static     │    │   Git        │    │   Pattern    │    │  Confidence  │    │   Output     │
│   Analysis   │───▶│   History    │───▶│   Detection  │───▶│   Scoring    │───▶│   Rendering  │
│              │    │   Mining     │    │              │    │              │    │              │
│ • imports    │    │ • death      │    │ • TODO:      │    │ • 14 signals │    │ • Rich panel │
│ • call sites │    │   commit     │    │   remove     │    │ • 0-100%     │    │ • JSON       │
│ • dynamic    │    │ • PR number  │    │ • DEPRECATED │    │ • risk label │    │ • plain text │
│ • reflection │    │ • author     │    │ • keep for   │    │              │    │              │
│              │    │ • blame      │    │   now        │    │              │    │              │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

### Confidence Score

The confidence score aggregates 14 weighted signals:

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
| File modified < 30 days ago | −20 | Negative |
| "Keep for now" unresolved | −15 | Negative |
| Language unknown (fallback) | −15 | Negative |
| Test file references found | −10 | Negative |
| Death commit ambiguous | −10 | Negative |

**Risk labels:** `85–100%` High Confidence · Low Risk  ·  `70–84%` Medium-High  ·  `55–69%` Medium  ·  `<55%` Low Confidence · High Risk

## Commands

### `fossil explain <file>`

Full forensic report for a single file.

```bash
fossil explain src/billing/legacy.py              # Rich panel output
fossil explain src/billing/legacy.py --json        # JSON output
fossil explain src/billing/legacy.py --plain       # Plain text
fossil explain src/billing/legacy.py --no-cache    # Skip cache
fossil explain src/billing/legacy.py --depth 2000  # Deeper git history
```

| Flag | Default | Description |
|------|---------|-------------|
| `--json` | false | Machine-readable JSON output |
| `--plain` | false | Plain text (no Rich formatting) |
| `--no-color` | false | Disable ANSI colors |
| `--no-cache` | false | Skip cache read/write |
| `--depth N` | 500 | Max git commits to traverse |
| `--remote` | auto | Force remote: `github`, `gitlab`, `none`, `auto` |
| `--yolo` | false | Create deletion PR if confidence ≥ 90% |
| `--force-yolo` | false | Create deletion PR regardless of confidence |
| `--narrate` | false | LLM narration (requires provider config) |

### `fossil scan [directory]`

Scan a directory for all dead files above a confidence threshold.

```bash
fossil scan ./src                       # Scan with default 70% threshold
fossil scan ./src --threshold 85        # Only high-confidence results
fossil scan ./src --language py,js      # Filter by language
fossil scan ./src --exclude "**/test*"  # Exclude patterns
fossil scan ./src --json                # JSON for CI pipelines
```

### `fossil clean [directory]`

Prioritized deletion backlog — ranked by confidence.

```bash
fossil clean ./src --threshold 80       # Show deletion candidates
fossil clean ./src --dry-run            # Preview what would be done
fossil clean ./src --json               # Machine-readable output
```

### `fossil config`

```bash
fossil config set github_token ghp_xxxx    # Store GitHub token
fossil config set llm_provider openai      # Configure LLM provider
fossil config show                          # Show config (tokens masked)
```

### `fossil cache`

```bash
fossil cache clear    # Delete analysis cache
fossil cache stats    # Show cache statistics
```

## Exit Codes

| Code | Meaning | CI Use |
|------|---------|--------|
| `0` | Dead code found, report generated | Fail CI check |
| `1` | Unexpected error | Fail CI check |
| `2` | File not found | Fail CI check |
| `3` | Not a git repository | Fail CI check |
| `4` | File is NOT dead (actively used) | Pass CI check |

## CI Integration

### GitHub Actions

```yaml
- name: Check for dead code
  run: |
    pip install fossil-code
    fossil scan . --threshold 90 --json > dead_report.json
    # Exit 0 = dead code found above 90% → fail the step
    # Exit 4 = no dead code above 90% → pass
```

### Pre-commit Hook

```bash
#!/bin/bash
fossil scan . --threshold 90 --json --no-cache > /dev/null 2>&1
if [ $? -eq 0 ]; then
  echo "⚠️  Dead code detected above 90% confidence. Run 'fossil scan .' for details."
  exit 1
fi
```

## Configuration

### User Config: `~/.config/fossil/config.toml`

```toml
github_token = ""
gitlab_token = ""
llm_api_key = ""
llm_provider = "openai"
llm_model = "gpt-4o-mini"
default_depth = 500
cache_ttl_hours = 24
```

### Project Config: `.fossil.toml`

Commit this to your repo root so the whole team shares settings:

```toml
[analysis]
languages = ["py", "js", "ts"]
exclude_patterns = ["**/migrations/**", "**/generated/**"]

[thresholds]
minimum_confidence = 70
yolo_minimum_confidence = 90

[pr]
base_branch = "main"
pr_labels = ["dead-code-cleanup", "automated"]
```

### Environment Variables

All environment variables override config file values:

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | GitHub API authentication |
| `GITLAB_TOKEN` | GitLab API authentication |
| `FOSSIL_LLM_API_KEY` | LLM provider API key |
| `FOSSIL_LLM_PROVIDER` | LLM provider (`openai` / `anthropic` / `ollama`) |
| `FOSSIL_LLM_MODEL` | LLM model name |
| `NO_COLOR` | Disable ANSI colors ([no-color.org](https://no-color.org)) |

## Language Support

| Language | Analyzer | Capability |
|----------|----------|------------|
| **Python** | `ast` module | Deep import, call, dynamic import, reflection analysis |
| JavaScript | Text fallback | Filename/symbol reference search |
| TypeScript | Text fallback | Filename/symbol reference search |
| Java | Text fallback | Filename/symbol reference search |
| Go | Text fallback | Filename/symbol reference search |
| Other | Text fallback | Filename reference search |

> **Python** gets the deepest analysis via the `ast` module. Other languages use conservative text-based reference search as a fallback. tree-sitter integration for deeper multi-language analysis is planned.

## Offline by Default

`fossil` works with **zero network access**. The core analysis pipeline (static analysis → git mining → pattern detection → confidence scoring) runs entirely offline.

Network is only used for three **optional** features:
- GitHub/GitLab API — PR title/body lookup, `--yolo` PR creation
- LLM API — `--narrate` natural language explanation

## Development

```bash
git clone https://github.com/iamvvek/fossil.git
cd fossil
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests (85+ tests)
pytest -v

# Lint
ruff check src/ tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development guide.

## Roadmap

- [x] **Phase 1** — Python forensics with Rich output
- [x] **Phase 2** — Multi-language scan, pattern detection, parallel processing
- [ ] **Phase 3** — GitHub/GitLab API integration, `--yolo` PR creation
- [ ] **Phase 4** — LLM narration, VS Code extension

## License

[MIT](LICENSE) — use it, fork it, ship it.
