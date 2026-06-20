"""Output rendering — Rich terminal panels and plain-text fallback.

Implements the Terminal UX Specification from §4 of the pre-development docs:
- Rich formatted panels with color-coded sections for `fossil explain`
- Table output for `fossil scan`
- Plain text fallback when Rich is unavailable or --plain is passed
- JSON rendering (unchanged)
"""
from __future__ import annotations

import contextlib
import json
import os
from typing import TYPE_CHECKING

from fossil.models import ForensicResult

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------

def render_json(result: ForensicResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Detect Rich availability
# ---------------------------------------------------------------------------

def _rich_available() -> bool:
    try:
        from rich.console import Console  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Rich terminal renderer (§4.1)
# ---------------------------------------------------------------------------

def render_rich(result: ForensicResult, *, no_color: bool = False) -> str:
    """Render a forensic report using Rich panels, tables, and colors."""
    from io import StringIO

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    buf = StringIO()
    console = Console(file=buf, width=90, no_color=no_color, force_terminal=True)

    # ── Status line ──
    status_color = "bold red" if result.dead else "bold green"
    status_dot = "●" if result.dead else "○"
    status_text = Text()
    status_text.append("  FORENSIC REPORT  ", style="bold white")
    status_text.append(result.target, style="cyan")
    status_text.append("\n")
    status_text.append("  Status  ", style="dim")
    status_text.append(f"{status_dot} {result.status}", style=status_color)
    status_text.append("   Language  ", style="dim")
    status_text.append(result.language.title(), style="white")

    sections = [status_text]

    # ── History section ──
    if result.git_history.tracked:
        hist = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        hist.add_column("key", style="dim", width=16, no_wrap=True)
        hist.add_column("value")
        if result.git_history.death_commit:
            dc = result.git_history.death_commit
            hash_text = Text(dc.short_hash, style="cyan")
            msg = f'  "{dc.message[:60]}"'
            hist.add_row("Dead since", Text.assemble(dc.date[:10], style="white"))
            hist.add_row("Death commit", Text.assemble(hash_text, msg))
            if dc.pr_number:
                hist.add_row("PR", Text(f"#{dc.pr_number} · {dc.message[:55]}", style="white"))
        elif result.git_history.ambiguous_death:
            hist.add_row("Death commit", Text("AMBIGUOUS — no single death commit found", style="yellow"))
        if result.git_history.original_author:
            oa = result.git_history.original_author
            hist.add_row("Original by", Text(f"{oa.author_name} · first committed {oa.date[:10]}", style="dim white"))
        sections.append(Panel(hist, title="[bold white]History[/bold white]", border_style="dim"))

    # ── Temporary Hold section ──
    if result.temporary_hold.detected:
        hold_parts: list[Text] = []
        for pat in result.temporary_hold.patterns:
            status_icon = "✓" if pat.condition_met is True else "✗" if pat.condition_met is False else "⚠"
            icon_style = "green" if pat.condition_met is True else "red" if pat.condition_met is False else "yellow"
            line = Text()
            line.append("  Pattern  ", style="dim")
            line.append(f'"{pat.text[:70]}" (line {pat.line})', style="white")
            line.append("\n  Status   ", style="dim")
            line.append(f"{status_icon} ", style=icon_style)
            status_label = "RESOLVED" if pat.condition_met is True else "UNRESOLVED" if pat.condition_met is False else "UNVERIFIED"
            line.append(status_label, style=icon_style)
            line.append(f"  —  {pat.evidence}", style="dim white")
            hold_parts.append(line)
        hold_text = Text("\n").join(hold_parts)
        sections.append(Panel(hold_text, title="[bold white]Temporary Hold[/bold white]", border_style="dim"))

    # ── Static Analysis section ──
    sa = result.static_analysis
    sa_table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    sa_table.add_column("k1", style="dim", width=20)
    sa_table.add_column("v1", width=8)
    sa_table.add_column("k2", style="dim", width=20)
    sa_table.add_column("v2", width=20)
    sa_table.add_row("Call sites", str(sa.call_sites), "Dynamic imports", str(len(sa.dynamic_references)))
    sa_table.add_row("Import refs", str(sa.import_references), "Reflection",
                     "None detected" if not sa.reflection_patterns else f"{len(sa.reflection_patterns)} detected")
    sa_table.add_row("Test references", str(sa.test_file_references), "Config refs", str(sa.config_file_references))
    sections.append(Panel(sa_table, title="[bold white]Static Analysis[/bold white]", border_style="dim"))

    # ── Confidence section ──
    if result.confidence:
        conf = result.confidence
        bar_filled = conf.score // 5
        bar_empty = 20 - bar_filled
        if conf.score >= 85:
            bar_style, label_style = "bold green", "bold green"
        elif conf.score >= 70 or conf.score >= 55:
            bar_style, label_style = "yellow", "yellow"
        else:
            bar_style, label_style = "red", "red"
        bar = Text()
        bar.append(f"   {conf.score}%  ", style="bold white")
        bar.append("█" * bar_filled, style=bar_style)
        bar.append("░" * bar_empty, style="dim")
        bar.append(f"  {conf.label.upper()} · {conf.risk.upper()}", style=label_style)
        sections.append(Panel(bar, title="[bold white]Confidence[/bold white]", border_style="dim"))

    # ── Suggested action ──
    if result.suggested_action:
        action = Text()
        action.append("  Suggested   ", style="dim")
        action.append(result.suggested_action, style="cyan")
        action.append("\n  Auto-PR     ", style="dim")
        action.append(result.yolo_command or "", style="cyan")
        sections.append(action)

    # ── Warnings ──
    if result.warnings:
        warn_text = Text()
        for w in result.warnings:
            warn_text.append(f"  ⚠ {w}\n", style="yellow")
        sections.append(warn_text)

    # ── Duration ──
    dur = Text(f"  Analysis duration: {result.analysis_duration_ms}ms", style="dim")
    if result.cached:
        dur.append("  (cached)", style="dim")
    sections.append(dur)

    # Build the main panel
    from rich.console import Group
    content = Group(*sections)
    panel = Panel(content, title="[bold cyan]fossil[/bold cyan]", border_style="cyan", padding=(1, 2))

    console.print(panel)
    return buf.getvalue()


def render_rich_scan(
    results: list[ForensicResult],
    repo_root: str,
    total_files: int,
    threshold: int,
    directory: str,
    *,
    no_color: bool = False,
) -> str:
    """Render scan results as a Rich table (§4.2)."""
    from io import StringIO
    from pathlib import Path

    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    buf = StringIO()
    console = Console(file=buf, width=100, no_color=no_color, force_terminal=True)

    if not results:
        console.print(f"[green]✓[/green] No dead code found above {threshold}% threshold.")
        return buf.getvalue()

    console.print(f"\n  fossil scan {directory}  ({total_files} files)\n")

    table = Table(show_edge=False, pad_edge=False, expand=True)
    table.add_column("File", style="cyan", ratio=5)
    table.add_column("Language", ratio=1)
    table.add_column("Dead Since", ratio=1)
    table.add_column("Confidence", justify="right", ratio=1)

    total_loc = 0
    for r in results:
        try:
            rel = Path(r.abs_path).relative_to(repo_root).as_posix()
        except ValueError:
            rel = r.target
        score = r.confidence.score if r.confidence else 0
        dead_since = ""
        if r.git_history.death_commit:
            dead_since = r.git_history.death_commit.date[:10]
        elif r.git_history.last_modified:
            dead_since = r.git_history.last_modified.date[:10]

        if score >= 85:
            score_style = "bold green"
        elif score >= 70:
            score_style = "yellow"
        else:
            score_style = "red"

        table.add_row(rel, r.language.title(), dead_since, Text(f"{score}%", style=score_style))
        with contextlib.suppress(OSError):
            total_loc += sum(1 for _ in Path(r.abs_path).read_text(encoding="utf-8", errors="replace").splitlines())

    console.print(table)
    console.print(f"\n  {len(results)} dead files found above {threshold}% threshold.")
    if total_loc:
        console.print(f"  Estimated removable: ~{total_loc:,} LOC across {len(results)} files.\n")
    console.print("  Run [cyan]fossil explain <file>[/cyan] for full forensic report.")
    console.print("  Run [cyan]fossil clean --threshold 80[/cyan] to see a deletion backlog.\n")
    return buf.getvalue()


def render_rich_clean(
    results: list[ForensicResult],
    repo_root: str,
    threshold: int,
    directory: str,
    dry_run: bool,
    *,
    no_color: bool = False,
) -> str:
    """Render clean backlog using Rich."""
    from io import StringIO
    from pathlib import Path

    from rich.console import Console
    from rich.table import Table
    from rich.text import Text

    buf = StringIO()
    console = Console(file=buf, width=100, no_color=no_color, force_terminal=True)

    if not results:
        console.print(f"No deletion candidates found above {threshold}% threshold.")
        return buf.getvalue()

    mode_label = "[yellow]DRY RUN[/yellow]" if dry_run else "[bold]PLANNED[/bold]"
    console.print(f"\n  fossil clean {directory} — {mode_label}\n")

    table = Table(show_edge=False, expand=True)
    table.add_column("#", width=4, justify="right")
    table.add_column("File", style="cyan", ratio=4)
    table.add_column("Confidence", justify="right", ratio=1)
    table.add_column("Action", ratio=2)

    for idx, r in enumerate(results, 1):
        try:
            rel = Path(r.abs_path).relative_to(repo_root).as_posix()
        except ValueError:
            rel = r.target
        score = r.confidence.score if r.confidence else 0
        if score >= 85:
            score_style = "bold green"
        elif score >= 70:
            score_style = "yellow"
        else:
            score_style = "red"
        table.add_row(str(idx), rel, Text(f"{score}%", style=score_style), r.suggested_action or "")

    console.print(table)
    console.print()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Plain-text renderer (unchanged from original, used as fallback)
# ---------------------------------------------------------------------------

def render_text(result: ForensicResult) -> str:
    lines = [
        "fossil forensic report",
        f"Target: {result.target}",
        f"Status: {result.status}",
        f"Language: {result.language}",
        f"Repository: {result.repo_root}",
    ]
    if result.cached:
        lines.append("Cached: true")
    if result.git_history.death_commit:
        dc = result.git_history.death_commit
        pr = f" (PR #{dc.pr_number})" if dc.pr_number else ""
        lines.append(f"Death commit: {dc.short_hash} {dc.date} {dc.message}{pr}")
    elif result.git_history.tracked:
        lines.append("Death commit: AMBIGUOUS")
    if result.git_history.original_author:
        oa = result.git_history.original_author
        lines.append(f"Original author: {oa.author_name} <{oa.author_email}>")
    static = result.static_analysis
    lines.extend(
        [
            "",
            "Static analysis:",
            f"  Import references: {static.import_references}",
            f"  Call sites: {static.call_sites}",
            f"  Dynamic references: {len(static.dynamic_references)}",
            f"  Reflection patterns: {len(static.reflection_patterns)}",
            f"  Test references: {static.test_file_references}",
            f"  Documentation references: {static.documentation_references}",
        ]
    )
    if result.temporary_hold.detected:
        lines.append("")
        lines.append("Temporary hold patterns:")
        for pattern in result.temporary_hold.patterns:
            status = "resolved" if pattern.condition_met is True else "unresolved" if pattern.condition_met is False else "unverified"
            lines.append(f"  line {pattern.line}: {status}: {pattern.text}")
            lines.append(f"    evidence: {pattern.evidence}")
    if result.confidence:
        lines.extend(
            [
                "",
                f"Confidence: {result.confidence.score}% — {result.confidence.label} · {result.confidence.risk}",
                "Signals:",
            ]
        )
        for signal in result.confidence.signals:
            mark = "applied" if signal.applied else "skipped"
            lines.append(f"  {signal.name}: {signal.weight:+d} ({mark}) — {signal.reason}")
    if result.suggested_action:
        lines.append("")
        lines.append(f"Suggested: {result.suggested_action}")
        lines.append(f"Auto-PR: {result.yolo_command}")
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  {warning}" for warning in result.warnings)
    lines.append("")
    lines.append(f"Analysis duration: {result.analysis_duration_ms}ms")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dispatcher — pick Rich or plain based on environment/flags
# ---------------------------------------------------------------------------

def should_use_rich(*, plain: bool = False, no_color: bool = False, json_mode: bool = False) -> bool:
    """Determine whether to use Rich rendering."""
    if json_mode or plain:
        return False
    if os.environ.get("NO_COLOR") or os.environ.get("FOSSIL_NO_COLOR"):
        return _rich_available()  # Use Rich but with no_color=True
    return _rich_available()


def render_explain(result: ForensicResult, *, json_mode: bool = False, plain: bool = False, no_color: bool = False) -> str:
    """Render a single explain result with the best available renderer."""
    if json_mode:
        return render_json(result)
    no_color = no_color or bool(os.environ.get("NO_COLOR")) or bool(os.environ.get("FOSSIL_NO_COLOR"))
    if not plain and _rich_available():
        return render_rich(result, no_color=no_color)
    return render_text(result)
