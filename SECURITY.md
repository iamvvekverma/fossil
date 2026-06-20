# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.2.x   | ✅ Currently supported |
| < 0.2   | ❌ No longer supported |

## Reporting a Vulnerability

If you discover a security vulnerability in `fossil`, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email: **security@fossil-cli.dev** (or open a private security advisory on GitHub).

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 1 week
- **Fix release:** Within 2 weeks for critical issues

## Security Design

`fossil` is designed with the following security principles:

1. **No shell injection:** All git operations use list-based subprocess calls, never string interpolation with user input.
2. **Path traversal prevention:** All user-provided paths are resolved via `pathlib.Path.resolve()` and validated to be within the git repository root.
3. **Credential safety:** API keys never appear in exceptions, log output, debug output, or JSON responses. Config files are created with `0600` permissions.
4. **LLM data minimization:** By default, only structured metadata is sent to LLM APIs — never raw source code unless `--include-code` is explicitly passed with a consent prompt.
5. **No telemetry:** `fossil` makes zero outbound network connections beyond the three explicit optional services (GitHub API, GitLab API, LLM API). No analytics, no error reporting, no update checks.
6. **Local-only cache:** The SQLite cache is local to the repository and contains only analysis results — never credentials.
