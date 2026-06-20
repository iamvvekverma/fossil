# Language Support

`fossil` supports multiple programming languages through two analysis strategies:

## Deep Analysis (Python)

Python files (`.py`) are analyzed using Python's built-in `ast` module, which provides:

| Capability | Description |
|------------|-------------|
| **Import detection** | `import x`, `from x import y`, aliased imports |
| **Call site detection** | Direct function calls, method calls, class instantiation |
| **Exported symbol extraction** | Classes, functions, and module-level variables |
| **Dynamic import detection** | `importlib.import_module()`, `__import__()` |
| **Reflection detection** | `getattr()`, `hasattr()`, `setattr()`, `vars()` |
| **Module name resolution** | Dotted module paths (e.g., `src.billing.processor`) |

This provides high-confidence results for Python codebases.

## Text-Based Fallback (All Other Languages)

For languages without a dedicated AST parser, `fossil` uses conservative text-based reference search:

| Language | Extensions | Analysis |
|----------|-----------|----------|
| JavaScript | `.js`, `.jsx` | Filename and symbol text search |
| TypeScript | `.ts`, `.tsx` | Filename and symbol text search |
| Java | `.java` | Filename and symbol text search |
| Go | `.go` | Filename and symbol text search |
| Unknown | Any other | Filename reference search only |

### How text-based analysis works

1. Extract the target file's **stem** (filename without extension) and **module path**
2. Search all other files in the repository for references to these names using word-boundary regex
3. Classify references by file type:
   - Test files → `test_file_references` (does not count as "live")
   - Documentation (`.md`, `.rst`, `.txt`) → `documentation_references`
   - Config files (`.toml`, `.yaml`, `.json`) → `config_file_references`
   - Source files → `import_references` or `call_sites`

### Limitations of text fallback

- Cannot distinguish between a reference to the target file and a coincidental use of the same name
- Cannot detect dynamic imports or reflection patterns specific to the language
- May produce false positives for files with common names (e.g., `utils.py`, `helpers.js`)
- Confidence scores for non-Python files will have the `language_unknown_fallback` penalty (−15 points)

## Supported Reference Files

Beyond source code, `fossil` also checks these file types for references:

| Type | Extensions | Reference Kind |
|------|-----------|----------------|
| Documentation | `.md`, `.rst`, `.txt`, `.adoc` | `documentation_references` |
| Configuration | `.toml`, `.yaml`, `.yml`, `.json`, `.ini`, `.cfg` | `config_file_references` |

## Excluded Directories

The following directories are automatically skipped during analysis:

- `.git/`
- `.fossil/`
- `__pycache__/`
- `node_modules/`
- `dist/`
- `build/`
- `.venv/` / `venv/`

Additional exclusion patterns can be configured via `--exclude` flags or `.fossil.toml`:

```toml
[analysis]
exclude_patterns = ["**/migrations/**", "**/generated/**", "**/*.pb.py"]
```

## Future: tree-sitter Integration

Planned for a future release: [tree-sitter](https://tree-sitter.github.io/) grammar integration for language-specific AST analysis of JavaScript, TypeScript, Java, and Go. This will bring Python-level analysis depth to all supported languages.
