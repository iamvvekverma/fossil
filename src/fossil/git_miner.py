from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from fossil.models import CommitInfo, GitHistoryResult
from fossil.repo import git_head, is_shallow, is_tracked, relpath, remote_url, run_git

PR_RE = re.compile(r"(?:#|PR\s*#?|pull request\s*#?)(\d+)", re.IGNORECASE)


def parse_commit(raw: str) -> CommitInfo:
    h, ts, author, email, subject = raw.split("\x1f", 4)
    date = datetime.fromtimestamp(int(ts), UTC).isoformat().replace("+00:00", "Z")
    pr_match = PR_RE.search(subject)
    return CommitInfo(
        hash=h,
        short_hash=h[:7],
        date=date,
        author_name=author,
        author_email=email,
        message=subject,
        pr_number=int(pr_match.group(1)) if pr_match else None,
    )


def mine_history(path: Path, repo_root: Path, depth: int, reference_terms: set[str]) -> GitHistoryResult:
    rel = relpath(path, repo_root)
    result = GitHistoryResult(
        head=git_head(repo_root),
        tracked=is_tracked(path, repo_root),
        shallow=is_shallow(repo_root),
        remote_url=remote_url(repo_root),
    )
    if result.shallow:
        result.warnings.append("Shallow git clone detected. History may be incomplete.")
    if not result.tracked:
        return result

    fmt = "%H%x1f%ct%x1f%an%x1f%ae%x1f%s"
    file_log = run_git(repo_root, ["log", f"--max-count={depth}", f"--format={fmt}", "--follow", "--", rel], check=False)
    commits = [parse_commit(line) for line in file_log.stdout.splitlines() if line.strip()]
    if commits:
        result.last_modified = commits[0]
        result.original_author = commits[-1]
    if len(commits) >= depth:
        result.warnings.append(f"History truncated at {depth} commits. Increase --depth for deeper traversal.")

    terms = [term for term in reference_terms if term]
    if not terms:
        result.ambiguous_death = True
        return result
    grep = "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
    ref_log = run_git(
        repo_root,
        ["log", "--all", f"--max-count={depth}", f"--format={fmt}", "-G", grep, "--", "."],
        check=False,
    )
    ref_commits = [parse_commit(line) for line in ref_log.stdout.splitlines() if line.strip()]
    candidates = [commit for commit in ref_commits if commit.hash != (result.last_modified.hash if result.last_modified else "")]
    if candidates:
        result.death_commit = candidates[0]
    else:
        result.ambiguous_death = True
    return result

