---
name: good first issue
about: Pre-written starter issues for new contributors
---

# Good First Issues for Contributors

Create the following issues on GitHub after pushing. Label each with `good first issue` and `help wanted`.

---

## Issue 1: Add Ruby file extension support

**Title:** `Add .rb (Ruby) to supported file extensions`
**Labels:** `good first issue`, `help wanted`, `enhancement`
**Body:**

```
fossil currently supports Python, JavaScript, TypeScript, Java, and Go files.
Ruby `.rb` files should be recognized and analyzed using the existing text-based fallback analyzer.

### What to do
1. Add `.rb` to `SOURCE_EXTENSIONS` in `src/fossil/analyzers.py`
2. Map it to language name `"ruby"` in `language_for()`
3. Add a test in `tests/test_analyzers.py` verifying `.rb` files are detected
4. Update `docs/LANGUAGE_SUPPORT.md`

### Helpful context
- Look at how `.go` is registered — Ruby follows the same pattern
- The text fallback analyzer handles everything automatically once the extension is registered
- Run `pytest tests/test_analyzers.py -v` to verify

**Estimated effort:** ~30 minutes
```

---

## Issue 2: Add Rust file extension support

**Title:** `Add .rs (Rust) to supported file extensions`
**Labels:** `good first issue`, `help wanted`, `enhancement`
**Body:**

```
Same as Ruby — add `.rs` Rust files to the text-based fallback analyzer.

### What to do
1. Add `.rs` to `SOURCE_EXTENSIONS` in `src/fossil/analyzers.py`
2. Map it to language name `"rust"` in `language_for()`
3. Add a test in `tests/test_analyzers.py`
4. Update `docs/LANGUAGE_SUPPORT.md`

**Estimated effort:** ~30 minutes
```

---

## Issue 3: Add `--version` output to `fossil explain --json`

**Title:** `Include fossil version in JSON output`
**Labels:** `good first issue`, `help wanted`, `enhancement`
**Body:**

```
When running `fossil explain <file> --json`, the output does not include the fossil version.
Adding a `"fossil_version"` key to the JSON output helps with debugging and reproducibility.

### What to do
1. In `src/fossil/render.py`, find the JSON rendering path
2. Add `"fossil_version": __version__` to the JSON dict
3. Add a test verifying the key appears in JSON output

**Estimated effort:** ~30 minutes
```

---

## Issue 4: Improve error message for unsupported file types

**Title:** `Better error message when analyzing unsupported file types`
**Labels:** `good first issue`, `help wanted`, `enhancement`
**Body:**

```
Running `fossil explain README.md` should give a clear message like:
"README.md is not a supported source file. Supported: .py, .js, .ts, .java, .go"

Currently it may produce confusing output or silently fail.

### What to do
1. In `src/fossil/cli.py` `cmd_explain()`, check if the file extension is in `SOURCE_EXTENSIONS`
2. If not, print a helpful error and return exit code 1
3. Add a test for this case

**Estimated effort:** ~45 minutes
```

---

## Issue 5: Add `--quiet` flag to suppress non-essential output

**Title:** `Add --quiet flag for minimal output`
**Labels:** `good first issue`, `help wanted`, `enhancement`
**Body:**

```
Add a `--quiet` / `-q` flag to `fossil scan` and `fossil clean` that suppresses
the progress bar and only outputs the final result. Useful for scripting.

### What to do
1. Add `--quiet` argument to scan and clean parsers in `src/fossil/cli.py`
2. Pass it through to suppress the Rich progress bar
3. Add tests

**Estimated effort:** ~1 hour
```

---

## Issue 6: Add man page / `--help` improvements

**Title:** `Improve --help descriptions and add examples`
**Labels:** `good first issue`, `help wanted`, `documentation`
**Body:**

```
The `--help` output for each subcommand could include a brief usage example.
argparse supports `epilog` for adding examples after the help text.

### What to do
1. Add `epilog` with usage examples to each subparser in `src/fossil/cli.py`
2. Use `formatter_class=argparse.RawDescriptionHelpFormatter` so examples render correctly

**Estimated effort:** ~30 minutes
```
