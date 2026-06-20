from __future__ import annotations

import subprocess
from pathlib import Path


class FossilError(Exception):
    exit_code = 1


class FileMissingError(FossilError):
    exit_code = 2


class NotGitRepositoryError(FossilError):
    exit_code = 3


def run_git(
    repo_root: Path | None, args: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    cmd = ["git"]
    if repo_root is not None:
        cmd.extend(["-C", str(repo_root)])
    cmd.extend(args)
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def find_repo_root(path: Path) -> Path:
    probe = path if path.is_dir() else path.parent
    try:
        result = run_git(probe, ["rev-parse", "--show-toplevel"])
    except subprocess.CalledProcessError as exc:
        raise NotGitRepositoryError("Not a git repository") from exc
    return Path(result.stdout.strip()).resolve()


def resolve_target(target: str) -> tuple[Path, Path, bool]:
    raw = Path(target).expanduser()
    if not raw.exists():
        raise FileMissingError(f"File not found: {target}")
    symlink = raw.is_symlink()
    path = raw.resolve()
    repo_root = find_repo_root(path)
    try:
        path.relative_to(repo_root)
    except ValueError as exc:
        raise NotGitRepositoryError(f"Path is outside git repository: {path}") from exc
    return path, repo_root, symlink


def relpath(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def is_tracked(path: Path, repo_root: Path) -> bool:
    result = run_git(
        repo_root, ["ls-files", "--error-unmatch", relpath(path, repo_root)], check=False
    )
    return result.returncode == 0


def is_gitignored(path: Path, repo_root: Path) -> bool:
    result = run_git(repo_root, ["check-ignore", "-q", relpath(path, repo_root)], check=False)
    return result.returncode == 0


def git_head(repo_root: Path) -> str:
    result = run_git(repo_root, ["rev-parse", "HEAD"], check=False)
    if result.returncode != 0:
        return "NO_HEAD"
    return result.stdout.strip()


def remote_url(repo_root: Path) -> str | None:
    result = run_git(repo_root, ["remote", "get-url", "origin"], check=False)
    return result.stdout.strip() or None if result.returncode == 0 else None


def is_shallow(repo_root: Path) -> bool:
    result = run_git(repo_root, ["rev-parse", "--is-shallow-repository"], check=False)
    return result.stdout.strip().lower() == "true"
