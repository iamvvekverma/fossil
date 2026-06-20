from __future__ import annotations

from datetime import UTC, datetime

from fossil.models import (
    ConfidenceResult,
    ConfidenceSignal,
    GitHistoryResult,
    PatternResult,
    StaticAnalysisResult,
)


def score(static: StaticAnalysisResult, git: GitHistoryResult, patterns: PatternResult) -> ConfidenceResult:
    signals: list[ConfidenceSignal] = []
    total = 0

    def add(name: str, weight: int, applied: bool, reason: str) -> None:
        nonlocal total
        signals.append(ConfidenceSignal(name, weight, applied, reason))
        if applied:
            total += weight

    zero_refs = static.call_sites == 0 and static.import_references == 0
    add("zero_call_sites", 30, zero_refs, "No main-code imports or calls found.")
    add("no_dynamic_references", 20, not static.dynamic_references, "No importlib/__import__ references found.")
    add("death_commit_identified", 15, git.death_commit is not None, "Git history contains a reference-removal candidate.")
    resolved = patterns.detected and all(p.condition_met is True for p in patterns.patterns)
    add("temporary_hold_resolved", 10, resolved, "All deferred deletion conditions are resolved.")
    add("no_reflection_patterns", 10, not static.reflection_patterns, "No matching getattr/hasattr/setattr references found.")

    dead_days = _days_since(git.death_commit.date if git.death_commit else None)
    add("file_age_over_90_days_dead", 8, dead_days is not None and dead_days > 90, "Death commit is older than 90 days.")
    add("pr_or_migration_context_found", 7, bool(git.death_commit and git.death_commit.pr_number), "Death commit references a PR.")

    add("dynamic_import_detected", -30, bool(static.dynamic_references), "Dynamic imports reduce static certainty.")
    add("reflection_detected", -20, bool(static.reflection_patterns), "Reflection patterns reduce static certainty.")
    add("test_file_references_found", -10, static.test_file_references > 0, "Only tests reference this target.")
    unresolved_hold = patterns.detected and any(p.condition_met is not True for p in patterns.patterns)
    add("keep_for_now_unresolved", -15, unresolved_hold, "At least one deferred deletion condition is unresolved.")
    add("language_unknown_fallback", -15, static.unknown_language, "Fallback text analysis is less precise.")
    modified_days = _days_since(git.last_modified.date if git.last_modified else None)
    add("file_modified_under_30_days_ago", -20, modified_days is not None and modified_days < 30, "Recently modified file.")
    add("death_commit_ambiguous", -10, git.ambiguous_death, "No single death commit was identified.")

    final = max(0, min(100, total))
    if final >= 85:
        label, risk = "High Confidence", "Low Risk"
    elif final >= 70:
        label, risk = "Medium-High Confidence", "Low-Medium Risk"
    elif final >= 55:
        label, risk = "Medium Confidence", "Medium Risk"
    else:
        label, risk = "Low Confidence", "High Risk"
    return ConfidenceResult(final, label, risk, signals)


def _days_since(value: str | None) -> int | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(UTC) - dt).days

