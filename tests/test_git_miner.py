"""Tests for the git history miner.

Covers §2.3 edge cases:
- Commit parsing from git log format
- PR number extraction from commit messages
- Death commit identification
- History depth truncation warning
- Shallow clone detection
- Untracked file handling
"""

from __future__ import annotations

from conftest import commit_all


def test_parse_commit_basic():
    from fossil.git_miner import parse_commit

    raw = "abc123def456\x1f1700000000\x1fJane Doe\x1fjane@example.com\x1fMigrate billing (#42)"
    commit = parse_commit(raw)
    assert commit.hash == "abc123def456"
    assert commit.short_hash == "abc123d"
    assert commit.author_name == "Jane Doe"
    assert commit.author_email == "jane@example.com"
    assert commit.pr_number == 42
    assert "Migrate billing" in commit.message


def test_parse_commit_no_pr():
    from fossil.git_miner import parse_commit

    raw = "abc123def456\x1f1700000000\x1fJohn\x1fjohn@example.com\x1fRefactor code"
    commit = parse_commit(raw)
    assert commit.pr_number is None


def test_parse_commit_pr_patterns():
    from fossil.git_miner import PR_RE

    # Various PR reference formats
    assert PR_RE.search("Fix bug (#123)").group(1) == "123"
    assert PR_RE.search("PR #456 - fix").group(1) == "456"
    assert PR_RE.search("PR456 merged").group(1) == "456"
    assert PR_RE.search("pull request #789").group(1) == "789"


def test_mine_history_tracked_file(make_repo):
    from fossil.git_miner import mine_history

    repo = make_repo()
    (repo / "legacy.py").write_text("class Legacy:\n    pass\n", encoding="utf-8")
    (repo / "main.py").write_text("from legacy import Legacy\n", encoding="utf-8")
    commit_all(repo, "Add legacy")
    (repo / "main.py").write_text("print('new code')\n", encoding="utf-8")
    commit_all(repo, "Remove legacy usage (#10)")

    result = mine_history(repo / "legacy.py", repo, depth=500, reference_terms={"legacy", "Legacy"})
    assert result.tracked is True
    assert result.original_author is not None
    assert result.last_modified is not None
    assert not result.shallow


def test_mine_history_untracked_file(make_repo):
    from fossil.git_miner import mine_history

    repo = make_repo()
    (repo / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")
    (repo / "untracked.py").write_text("y = 2\n", encoding="utf-8")

    result = mine_history(repo / "untracked.py", repo, depth=500, reference_terms={"untracked"})
    assert result.tracked is False


def test_mine_history_depth_warning(make_repo):
    from fossil.git_miner import mine_history

    repo = make_repo()
    (repo / "file.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "commit 1")
    (repo / "file.py").write_text("x = 2\n", encoding="utf-8")
    commit_all(repo, "commit 2")
    (repo / "file.py").write_text("x = 3\n", encoding="utf-8")
    commit_all(repo, "commit 3")

    # Use depth=2 so the 3 commits hit the limit
    result = mine_history(repo / "file.py", repo, depth=2, reference_terms={"file"})
    assert any("truncated" in w.lower() for w in result.warnings)


def test_mine_history_empty_terms(make_repo):
    from fossil.git_miner import mine_history

    repo = make_repo()
    (repo / "file.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = mine_history(repo / "file.py", repo, depth=500, reference_terms=set())
    assert result.ambiguous_death is True
