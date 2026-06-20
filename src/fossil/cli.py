"""Root CLI — command parser, dispatch, and user-facing error handling.

Implements §3.4 of the pre-development docs:
- fossil explain <target> — full forensic report
- fossil scan [directory] — directory scan with threshold filtering
- fossil clean [directory] — prioritized deletion backlog
- fossil cache clear — delete cache
- fossil cache stats — show cache statistics
- fossil config set/show — credential management
- Global flags: --no-color, --plain, --version
- Exit codes: 0 (dead), 1 (error), 2 (file not found), 3 (not git repo), 4 (alive/no results), 5 (unsupported)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fossil import __version__
from fossil.analyzers import SOURCE_EXTENSIONS, iter_repo_files, language_for
from fossil.cache import CacheStore
from fossil.config_manager import masked_config, read_project_config, set_config
from fossil.engine import explain
from fossil.render import (
    render_explain,
    render_rich_clean,
    render_rich_scan,
)
from fossil.repo import FileMissingError, FossilError, NotGitRepositoryError, find_repo_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fossil", description="Dead-code forensics CLI")
    parser.add_argument("--version", action="version", version=f"fossil {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── fossil explain ──
    explain_p = sub.add_parser("explain", help="Generate a forensic report for one file")
    explain_p.add_argument("target")
    explain_p.add_argument("--json", action="store_true")
    explain_p.add_argument("--plain", action="store_true")
    explain_p.add_argument("--no-color", action="store_true")
    explain_p.add_argument("--no-cache", action="store_true")
    explain_p.add_argument("--depth", type=int, default=500)
    explain_p.add_argument("--remote", choices=["github", "gitlab", "none", "auto"], default="auto")
    explain_p.add_argument("--narrate", action="store_true")
    explain_p.add_argument("--include-code", action="store_true")
    explain_p.add_argument("--yolo", action="store_true")
    explain_p.add_argument("--force-yolo", action="store_true")
    explain_p.set_defaults(func=cmd_explain)

    # ── fossil scan ──
    scan_p = sub.add_parser("scan", help="Scan a directory for dead files")
    scan_p.add_argument("directory", nargs="?", default=".")
    scan_p.add_argument("--threshold", type=int, default=70)
    scan_p.add_argument("--language", default="all")
    scan_p.add_argument("--exclude", action="append", default=[])
    scan_p.add_argument("--json", action="store_true")
    scan_p.add_argument("--plain", action="store_true")
    scan_p.add_argument("--no-color", action="store_true")
    scan_p.add_argument("--no-cache", action="store_true")
    scan_p.add_argument("--depth", type=int, default=500)
    scan_p.set_defaults(func=cmd_scan)

    # ── fossil clean ──
    clean_p = sub.add_parser("clean", help="Build a prioritized deletion backlog")
    clean_p.add_argument("directory", nargs="?", default=".")
    clean_p.add_argument("--threshold", type=int, default=80)
    clean_p.add_argument("--dry-run", action="store_true")
    clean_p.add_argument("--yolo", action="store_true")
    clean_p.add_argument("--json", action="store_true")
    clean_p.add_argument("--plain", action="store_true")
    clean_p.add_argument("--no-color", action="store_true")
    clean_p.add_argument("--no-cache", action="store_true")
    clean_p.add_argument("--depth", type=int, default=500)
    clean_p.set_defaults(func=cmd_clean)

    # ── fossil cache ──
    cache_p = sub.add_parser("cache", help="Cache operations")
    cache_sub = cache_p.add_subparsers(dest="cache_command", required=True)
    clear_p = cache_sub.add_parser("clear")
    clear_p.set_defaults(func=cmd_cache_clear)
    stats_p = cache_sub.add_parser("stats")
    stats_p.set_defaults(func=cmd_cache_stats)

    # ── fossil config ──
    config_p = sub.add_parser("config", help="Configuration operations")
    config_sub = config_p.add_subparsers(dest="config_command", required=True)
    show_p = config_sub.add_parser("show")
    show_p.set_defaults(func=cmd_config_show)
    set_p = config_sub.add_parser("set")
    set_p.add_argument("key")
    set_p.add_argument("value")
    set_p.set_defaults(func=cmd_config_set)
    return parser


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_explain(args: argparse.Namespace) -> int:
    if args.narrate:
        print("--narrate requires a configured LLM provider. Run: fossil config set llm_provider openai", file=sys.stderr)
        return 1
    result = explain(args.target, depth=args.depth, no_cache=args.no_cache)
    if args.yolo or args.force_yolo:
        min_score = 90 if args.yolo and not args.force_yolo else 0
        score = result.confidence.score if result.confidence else 0
        if score < min_score:
            print(f"Confidence is {score}%. --yolo blocked below 90%. Use --force-yolo to override.", file=sys.stderr)
            return 1
        print("--yolo PR generation requires GitHub/GitLab API integration; no files were changed.", file=sys.stderr)
        return 1
    output = render_explain(
        result,
        json_mode=args.json,
        plain=args.plain,
        no_color=args.no_color,
    )
    print(output)
    return 0 if result.dead else 4


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.directory).expanduser().resolve()
    repo_root = find_repo_root(root)

    # Read project config for exclude patterns
    project_config = read_project_config(repo_root)
    exclude = list(args.exclude)
    if project_config.get("analysis", {}).get("exclude_patterns"):
        exclude.extend(project_config["analysis"]["exclude_patterns"])

    selected = _language_filter(args.language)
    candidates = [
        path
        for path in iter_repo_files(root, exclude)
        if path.suffix.lower() in SOURCE_EXTENSIONS and (selected is None or language_for(path) in selected)
    ]

    if not candidates:
        if args.json:
            print(json.dumps([]))
        else:
            print(f"No supported source files found in {args.directory}. Supported: Python, JavaScript, TypeScript, Java, Go.")
        return 4

    # Analyze files with progress
    results = _analyze_files_parallel(candidates, args.depth, args.no_cache, args.threshold, args.plain)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2, sort_keys=True))
    else:
        use_rich = not args.plain and _rich_ok()
        if use_rich:
            output = render_rich_scan(
                results, str(repo_root), len(candidates), args.threshold, args.directory,
                no_color=args.no_color,
            )
            print(output)
        else:
            if not results:
                print(f"✓ No dead code found above {args.threshold}% threshold.")
                return 4
            print(f"fossil scan {args.directory} ({len(candidates)} files)")
            print(f"{'File':<50} {'Language':<12} {'Confidence':>10}  Status")
            print("─" * 85)
            for result in results:
                score = result.confidence.score if result.confidence else 0
                rel = Path(result.abs_path).relative_to(repo_root).as_posix()
                print(f"{rel:<50} {result.language:<12} {score:>9}%  {result.confidence.label}")
            print(f"\n{len(results)} dead files found above {args.threshold}% threshold.")

    return 0 if results else 4


def cmd_clean(args: argparse.Namespace) -> int:
    root = Path(args.directory).expanduser().resolve()
    repo_root = find_repo_root(root)

    # Read project config
    project_config = read_project_config(repo_root)
    exclude = []
    if project_config.get("analysis", {}).get("exclude_patterns"):
        exclude.extend(project_config["analysis"]["exclude_patterns"])

    candidates = [
        path
        for path in iter_repo_files(root, exclude)
        if path.suffix.lower() in SOURCE_EXTENSIONS
    ]
    results = _analyze_files_parallel(candidates, args.depth, args.no_cache, args.threshold, args.plain)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2, sort_keys=True))
    elif not results:
        print(f"No deletion candidates found above {args.threshold}% threshold.")
        return 4
    else:
        use_rich = not args.plain and _rich_ok()
        if use_rich:
            output = render_rich_clean(
                results, str(repo_root), args.threshold, args.directory,
                dry_run=args.dry_run or not args.yolo,
                no_color=args.no_color,
            )
            print(output)
        else:
            mode = "dry run" if args.dry_run or not args.yolo else "planned"
            print(f"fossil clean {args.directory} — {mode}")
            for index, result in enumerate(results, 1):
                score = result.confidence.score if result.confidence else 0
                rel = Path(result.abs_path).relative_to(repo_root).as_posix()
                print(f"{index}. {rel} — {score}% — {result.suggested_action}")

    if args.yolo:
        print("--yolo PR generation requires GitHub/GitLab API integration; no files were changed.", file=sys.stderr)
        return 1
    return 0 if results else 4


def _analyze_files_parallel(
    candidates: list[Path],
    depth: int,
    no_cache: bool,
    threshold: int,
    plain: bool,
) -> list:
    """Analyze files using ThreadPoolExecutor with optional Rich progress bar."""
    from fossil.engine import explain as explain_file

    results = []
    use_progress = not plain and _rich_ok() and len(candidates) > 3

    if use_progress:
        try:
            from rich.progress import (
                BarColumn,
                MofNCompleteColumn,
                Progress,
                SpinnerColumn,
                TextColumn,
            )
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Scanning..."),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("[dim]{task.description}"),
                transient=True,
            ) as progress:
                task = progress.add_task("", total=len(candidates))
                worker_count = min(32, (os.cpu_count() or 1) + 4)
                # Use parallel only if enough files
                if len(candidates) >= 10:
                    with ThreadPoolExecutor(max_workers=worker_count) as pool:
                        futures = {pool.submit(explain_file, str(p), depth=depth, no_cache=no_cache): p for p in candidates}
                        for future in as_completed(futures):
                            progress.advance(task)
                            try:
                                result = future.result()
                                if result.dead and result.confidence and result.confidence.score >= threshold:
                                    results.append(result)
                            except Exception:
                                pass
                else:
                    for path in candidates:
                        progress.advance(task)
                        try:
                            result = explain_file(str(path), depth=depth, no_cache=no_cache)
                            if result.dead and result.confidence and result.confidence.score >= threshold:
                                results.append(result)
                        except Exception:
                            pass
        except ImportError:
            use_progress = False

    if not use_progress:
        for path in candidates:
            try:
                result = explain_file(str(path), depth=depth, no_cache=no_cache)
                if result.dead and result.confidence and result.confidence.score >= threshold:
                    results.append(result)
            except Exception:
                pass

    results.sort(key=lambda r: r.confidence.score if r.confidence else 0, reverse=True)
    return results


def _language_filter(value: str) -> set[str] | None:
    if value == "all":
        return None
    mapping = {"py": "python", "js": "javascript", "ts": "typescript", "java": "java", "go": "go"}
    return {mapping.get(item.strip(), item.strip()) for item in value.split(",") if item.strip()}


def _rich_ok() -> bool:
    try:
        from rich.console import Console  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Cache & config commands
# ---------------------------------------------------------------------------

def cmd_cache_clear(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(Path.cwd())
    CacheStore(repo_root).clear()
    print("Cache cleared.")
    return 0


def cmd_cache_stats(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(Path.cwd())
    stats = CacheStore(repo_root).stats()
    print(f"Cache location: {repo_root / '.fossil' / 'cache.db'}")
    print(f"Size: {stats['size_bytes'] / 1024:.1f} KB")
    print(f"Analysis results cached: {stats['analysis_count']}")
    print(f"Scan results cached: {stats['scan_count']}")
    print(f"PR lookups cached: {stats['pr_count']}")
    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    values = masked_config()
    if not values:
        print("No fossil config values set.")
        return 0
    for key, value in sorted(values.items()):
        print(f"{key} = {value}")
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    set_config(args.key, args.value)
    print(f"✓ {args.key} saved.")
    return 0


# ---------------------------------------------------------------------------
# Entry point & error handling
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        code = args.func(args)
    except FileMissingError as exc:
        code = exc.exit_code
        _print_error(args, "File not found", str(exc), code)
    except NotGitRepositoryError as exc:
        code = exc.exit_code
        _print_error(args, "Not a git repository", str(exc), code)
    except FossilError as exc:
        code = exc.exit_code
        _print_error(args, "fossil error", str(exc), code)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        code = 1
        _print_error(args, "Unexpected error", str(exc), code)
    raise SystemExit(code)


def _print_error(args: argparse.Namespace, error: str, message: str, code: int) -> None:
    if getattr(args, "json", False):
        print(json.dumps({"error": error, "message": message, "code": code}, sort_keys=True))
    else:
        print(f"Error: {message}", file=sys.stderr)


if __name__ == "__main__":
    main()
