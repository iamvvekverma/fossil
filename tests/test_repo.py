"""Tests for repo utilities.

Covers repository detection, path resolution, and git operations.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from conftest import commit_all


def test_find_repo_root(make_repo):
    from fossil.repo import find_repo_root

    repo = make_repo()
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")

    root = find_repo_root(repo / "f.py")
    assert root == repo.resolve()


def test_find_repo_root_not_git(tmp_path: Path):
    from fossil.repo import NotGitRepositoryError, find_repo_root

    with pytest.raises(NotGitRepositoryError):
        find_repo_root(tmp_path)


def test_resolve_target_file_not_found(tmp_path: Path):
    from fossil.repo import FileMissingError, resolve_target

    with pytest.raises(FileMissingError):
        resolve_target(str(tmp_path / "nonexistent.py"))


def test_resolve_target_symlink(make_repo):
    from fossil.repo import resolve_target

    repo = make_repo()
    (repo / "real.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "link.py").symlink_to(repo / "real.py")
    commit_all(repo, "initial")

    path, root, symlink = resolve_target(str(repo / "link.py"))
    assert symlink is True
    assert path == (repo / "real.py").resolve()


def test_is_tracked(make_repo):
    from fossil.repo import is_tracked

    repo = make_repo()
    (repo / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")
    (repo / "untracked.py").write_text("y = 2\n", encoding="utf-8")

    assert is_tracked(repo / "tracked.py", repo) is True
    assert is_tracked(repo / "untracked.py", repo) is False


def test_is_gitignored(make_repo):
    from fossil.repo import is_gitignored

    repo = make_repo()
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    ignored = repo / "ignored"
    ignored.mkdir()
    (ignored / "file.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")

    assert is_gitignored(ignored / "file.py", repo) is True
    assert is_gitignored(repo / ".gitignore", repo) is False


def test_git_head(make_repo):
    from fossil.repo import git_head

    repo = make_repo()
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")

    head = git_head(repo)
    assert len(head) == 40  # Full SHA
    assert head != "NO_HEAD"


def test_is_shallow(make_repo):
    from fossil.repo import is_shallow

    repo = make_repo()
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")

    assert is_shallow(repo) is False


def test_relpath(make_repo):
    from fossil.repo import relpath

    repo = make_repo()
    assert relpath(repo / "src" / "main.py", repo) == "src/main.py"
