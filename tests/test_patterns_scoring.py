"""Tests for pattern detection and confidence scoring.

Covers §2.5 (pattern detection) and §2.6 (confidence scoring):
- TODO/FIXME pattern detection
- "keep for now" pattern detection
- DEPRECATED pattern detection
- Date condition verification
- Version/tag condition verification
- PR condition verification
- Confidence score computation with all signals
- Risk label assignment
"""
from __future__ import annotations

from pathlib import Path

from conftest import commit_all, git

# ---------------------------------------------------------------------------
# Pattern Detection Tests
# ---------------------------------------------------------------------------

def test_date_condition_resolution(tmp_path: Path):
    from fossil.patterns import verify_condition
    kind, met, evidence = verify_condition("2020-01-01", tmp_path)
    assert kind == "date"
    assert met is True
    assert "passed" in evidence


def test_date_condition_future(tmp_path: Path):
    from fossil.patterns import verify_condition
    kind, met, evidence = verify_condition("2099-12-31", tmp_path)
    assert kind == "date"
    assert met is False
    assert "not passed" in evidence.lower()


def test_unverifiable_condition(tmp_path: Path):
    from fossil.patterns import verify_condition
    kind, met, evidence = verify_condition("when the new billing system is stable", tmp_path)
    assert kind == "unverifiable"
    assert met is None
    assert "UNVERIFIABLE" in evidence


def test_empty_condition(tmp_path: Path):
    from fossil.patterns import verify_condition
    kind, met, evidence = verify_condition("", tmp_path)
    assert kind == "unverifiable"
    assert met is None


def test_version_condition_with_tag(make_repo):
    from fossil.patterns import verify_condition

    repo = make_repo()
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")
    git(repo, "tag", "v2.0.0")

    kind, met, evidence = verify_condition("v2.0.0", repo)
    assert kind == "version"
    assert met is True
    assert "tag" in evidence.lower()


def test_version_condition_without_tag(make_repo):
    from fossil.patterns import verify_condition

    repo = make_repo()
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")

    kind, met, evidence = verify_condition("v9.9.9", repo)
    assert kind == "version"
    assert met is False


def test_pr_condition_found_in_log(make_repo):
    from fossil.patterns import verify_condition

    repo = make_repo()
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "Fix billing (#55)")

    kind, met, evidence = verify_condition("PR #55 is merged", repo)
    assert kind == "pr"
    assert met is True
    assert "#55" in evidence


def test_detect_todo_remove_pattern(make_repo):
    from fossil.patterns import detect_patterns

    repo = make_repo()
    p = repo / "legacy.py"
    p.write_text("# TODO: remove after 2020-01-01\nclass Legacy:\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = detect_patterns(p, repo)
    assert result.detected is True
    assert len(result.patterns) >= 1
    assert result.patterns[0].condition_type == "date"
    assert result.patterns[0].condition_met is True


def test_detect_deprecated_pattern(make_repo):
    from fossil.patterns import detect_patterns

    repo = make_repo()
    p = repo / "old.py"
    p.write_text("# DEPRECATED\nclass Old:\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = detect_patterns(p, repo)
    assert result.detected is True
    assert any("DEPRECATED" in pat.text for pat in result.patterns)


def test_detect_keep_for_now(make_repo):
    from fossil.patterns import detect_patterns

    repo = make_repo()
    p = repo / "temp.py"
    p.write_text("# keeping this around for now\nclass Temp:\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = detect_patterns(p, repo)
    assert result.detected is True


def test_detect_temporary_keyword(make_repo):
    from fossil.patterns import detect_patterns

    repo = make_repo()
    p = repo / "fix.py"
    p.write_text("# temporary fix for billing\ndef patch():\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = detect_patterns(p, repo)
    assert result.detected is True


def test_detect_multiple_patterns(make_repo):
    from fossil.patterns import detect_patterns

    repo = make_repo()
    p = repo / "multi.py"
    p.write_text(
        "# DEPRECATED\n# TODO: remove after 2020-01-01\n# temporary\nclass Multi:\n    pass\n",
        encoding="utf-8",
    )
    commit_all(repo, "initial")

    result = detect_patterns(p, repo)
    assert result.detected is True
    assert len(result.patterns) >= 3


# ---------------------------------------------------------------------------
# Confidence Scoring Tests
# ---------------------------------------------------------------------------

def test_confidence_high_when_clearly_dead():
    from fossil.models import (
        CommitInfo,
        GitHistoryResult,
        PatternResult,
        StaticAnalysisResult,
    )
    from fossil.scoring import score

    static = StaticAnalysisResult(
        language="python",
        call_sites=0,
        import_references=0,
    )
    death = CommitInfo(
        hash="abc123", short_hash="abc123", date="2020-01-01T00:00:00Z",
        author_name="Test", author_email="t@t.com", message="Remove legacy (#42)", pr_number=42,
    )
    git_result = GitHistoryResult(
        head="HEAD",
        tracked=True,
        death_commit=death,
        last_modified=CommitInfo(
            hash="def456", short_hash="def456", date="2020-01-01T00:00:00Z",
            author_name="Test", author_email="t@t.com", message="last",
        ),
    )
    patterns = PatternResult(detected=False)

    result = score(static, git_result, patterns)
    assert result.score >= 80
    assert "High" in result.label or "Medium-High" in result.label
    assert "Low" in result.risk


def test_confidence_low_with_dynamic_imports():
    from fossil.models import (
        GitHistoryResult,
        PatternResult,
        Reference,
        StaticAnalysisResult,
    )
    from fossil.scoring import score

    static = StaticAnalysisResult(
        language="python",
        call_sites=0,
        import_references=0,
        dynamic_references=[Reference("loader.py", 1, "dynamic", "importlib.import_module('legacy')")],
        reflection_patterns=[Reference("caller.py", 5, "reflection", "getattr(mod, 'Legacy')")],
    )
    git_result = GitHistoryResult(head="HEAD", tracked=True, ambiguous_death=True)
    patterns = PatternResult(detected=False)

    result = score(static, git_result, patterns)
    # Dynamic + reflection penalties should substantially lower the score
    assert result.score < 60


def test_confidence_penalizes_unresolved_hold():
    from fossil.models import (
        GitHistoryResult,
        HoldPattern,
        PatternResult,
        StaticAnalysisResult,
    )
    from fossil.scoring import score

    static = StaticAnalysisResult(language="python", call_sites=0, import_references=0)
    git_result = GitHistoryResult(head="HEAD", tracked=True, ambiguous_death=True)
    patterns = PatternResult(
        detected=True,
        patterns=[
            HoldPattern(
                text="keep for now", line=1, condition="Q2 rollout",
                condition_type="unverifiable", condition_met=None, evidence="Cannot verify",
            )
        ],
    )

    result = score(static, git_result, patterns)
    # Unresolved hold should apply a penalty
    assert any(s.name == "keep_for_now_unresolved" and s.applied for s in result.signals)


def test_confidence_unknown_language_penalty():
    from fossil.models import GitHistoryResult, PatternResult, StaticAnalysisResult
    from fossil.scoring import score

    static = StaticAnalysisResult(language="unknown", call_sites=0, import_references=0, unknown_language=True)
    git_result = GitHistoryResult(head="HEAD", tracked=True, ambiguous_death=True)
    patterns = PatternResult(detected=False)

    result = score(static, git_result, patterns)
    assert any(s.name == "language_unknown_fallback" and s.applied for s in result.signals)


def test_risk_labels():
    from fossil.models import GitHistoryResult, PatternResult, StaticAnalysisResult
    from fossil.scoring import score

    # Create a result that should give low confidence (many penalties)
    static = StaticAnalysisResult(
        language="unknown",
        call_sites=0,
        import_references=0,
        unknown_language=True,
        dynamic_references=[],
        reflection_patterns=[],
    )
    git_result = GitHistoryResult(head="HEAD", tracked=True, ambiguous_death=True)
    patterns = PatternResult(detected=False)

    result = score(static, git_result, patterns)
    # Score should be positive due to zero_call_sites(+30) + no_dynamic(+20)
    # minus language_unknown(-15) minus ambiguous_death(-10)
    # The label should reflect the score range from §2.6
    if result.score >= 85:
        assert result.label == "High Confidence"
    elif result.score >= 70:
        assert result.label == "Medium-High Confidence"
    elif result.score >= 55:
        assert result.label == "Medium Confidence"
    else:
        assert result.label == "Low Confidence"
