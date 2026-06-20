from __future__ import annotations

import time

from fossil import __version__
from fossil.analyzers import analyze_file, module_names
from fossil.cache import CacheStore
from fossil.git_miner import mine_history
from fossil.models import ForensicResult
from fossil.patterns import detect_patterns
from fossil.repo import git_head, is_gitignored, is_tracked, relpath, resolve_target
from fossil.scoring import score


def explain(target: str, *, depth: int = 500, no_cache: bool = False) -> ForensicResult:
    start = time.perf_counter()
    path, repo_root, symlink = resolve_target(target)
    head = git_head(repo_root)
    cache = CacheStore(repo_root)
    if not no_cache:
        cached = cache.get_analysis(path, head, repo_root)
        if cached:
            return _from_dict(cached, cached=True)

    static = analyze_file(path, repo_root)
    tracked = is_tracked(path, repo_root)
    refs = module_names(path, repo_root) | {path.stem}
    git = mine_history(path, repo_root, depth, refs)
    patterns = detect_patterns(path, repo_root)
    warnings = list(git.warnings)
    if symlink:
        warnings.append(f"Target is a symlink; analyzed resolved path: {path}")
    if is_gitignored(path, repo_root):
        warnings.append("File is gitignored. Analysis may be incomplete.")

    if not tracked:
        confidence = None
        dead = False
        status = "UNTRACKED — No git history. Cannot determine death date."
    else:
        confidence = score(static, git, patterns)
        dead = static.import_references == 0 and static.call_sites == 0
        status = "DEAD" if dead else "LIVE"

    rel = relpath(path, repo_root)
    duration = int((time.perf_counter() - start) * 1000)
    result = ForensicResult(
        fossil_version=__version__,
        target=target,
        abs_path=str(path),
        repo_root=str(repo_root),
        language=static.language,
        dead=dead,
        status=status,
        static_analysis=static,
        git_history=git,
        temporary_hold=patterns,
        confidence=confidence,
        suggested_action=f"rm {rel}" if dead else None,
        yolo_command=f"fossil explain {rel} --yolo" if dead else None,
        analysis_duration_ms=duration,
        warnings=warnings,
    )
    if not no_cache:
        cache.put_analysis(path, head, repo_root, __version__, result.to_dict())
    return result


def _from_dict(data: dict, cached: bool) -> ForensicResult:
    from fossil.models import (
        CommitInfo,
        ConfidenceResult,
        ConfidenceSignal,
        GitHistoryResult,
        HoldPattern,
        PatternResult,
        Reference,
        StaticAnalysisResult,
    )

    static_data = data["static_analysis"]
    static = StaticAnalysisResult(
        **{
            **static_data,
            "references": [Reference(**r) for r in static_data.get("references", [])],
            "dynamic_references": [Reference(**r) for r in static_data.get("dynamic_references", [])],
            "reflection_patterns": [Reference(**r) for r in static_data.get("reflection_patterns", [])],
        }
    )
    git_data = data["git_history"]
    for key in ("death_commit", "original_author", "last_modified"):
        if git_data.get(key):
            git_data[key] = CommitInfo(**git_data[key])
    git = GitHistoryResult(**git_data)
    pattern_data = data["temporary_hold"]
    patterns = PatternResult(
        detected=pattern_data.get("detected", False),
        patterns=[HoldPattern(**p) for p in pattern_data.get("patterns", [])],
    )
    confidence = None
    if data.get("confidence"):
        c = data["confidence"]
        confidence = ConfidenceResult(
            score=c["score"],
            label=c["label"],
            risk=c["risk"],
            signals=[ConfidenceSignal(**s) for s in c.get("signals", [])],
        )
    return ForensicResult(
        **{
            **data,
            "static_analysis": static,
            "git_history": git,
            "temporary_hold": patterns,
            "confidence": confidence,
            "cached": cached,
        }
    )

