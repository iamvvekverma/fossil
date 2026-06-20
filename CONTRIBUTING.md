# Contributing to fossil

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/iamvvekverma/fossil.git
cd fossil

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Verify installation
fossil --version
fossil --help

# Run the test suite
pytest -v
```

## Project Structure

```
fossil/
├── src/fossil/          # Main package
│   ├── cli.py           # CLI commands and argument parsing
│   ├── engine.py        # Core analysis orchestration
│   ├── analyzers.py     # Static analysis (Python AST + text fallback)
│   ├── git_miner.py     # Git history traversal and death commit detection
│   ├── patterns.py      # Deferred-deletion pattern detection
│   ├── scoring.py       # Confidence score computation
│   ├── render.py        # Rich terminal output and JSON rendering
│   ├── cache.py         # SQLite result caching
│   ├── config_manager.py # Config file and env var management
│   ├── repo.py          # Git repository utilities
│   └── models.py        # Data models (dataclasses)
├── tests/               # Test suite (85+ tests)
├── docs/                # Documentation
└── pyproject.toml       # Build configuration
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test file
pytest tests/test_analyzers.py

# Run a specific test
pytest tests/test_analyzers.py::test_exported_symbols_python

# Run with coverage
pip install pytest-cov
pytest --cov=fossil --cov-report=term-missing
```

## Code Quality

We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for lint errors
ruff check src/ tests/

# Auto-fix lint errors
ruff check --fix src/ tests/

# Check formatting
ruff format --check src/ tests/

# Auto-format
ruff format src/ tests/
```

## Making Changes

### 1. Create a branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make your changes

- Follow the existing code style
- Add tests for new functionality
- Update documentation if needed

### 3. Test your changes

```bash
# Run the full test suite
pytest -v

# Run the linter
ruff check src/ tests/

# Test the CLI manually
fossil explain path/to/some/file.py
```

### 4. Commit and push

Write clear, descriptive commit messages:

```
Add support for Ruby static analysis

- Add RubyAnalyzer using text-based reference search
- Register .rb extension in SOURCE_EXTENSIONS
- Add tests for Ruby import detection
```

### 5. Open a Pull Request

- Fill out the PR template
- Link any related issues
- Wait for CI checks to pass

## Adding a New Language Analyzer

1. Add the file extension to `SOURCE_EXTENSIONS` in `analyzers.py`
2. If the language has a structured parser available, create a dedicated `_scan_<language>()` function
3. Otherwise, the existing text-based fallback (`_scan_text()`) handles it automatically
4. Add tests in `tests/test_analyzers.py`
5. Update `docs/LANGUAGE_SUPPORT.md`

## Reporting Bugs

Please use the [Bug Report template](https://github.com/iamvvekverma/fossil/issues/new?template=bug_report.yml) on GitHub.

Include:
- fossil version (`fossil --version`)
- Python version (`python --version`)
- Operating system
- Minimal reproduction steps
- Full terminal output

## Feature Requests

Use the [Feature Request template](https://github.com/iamvvekverma/fossil/issues/new?template=feature_request.yml).

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). Please read it before participating.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
