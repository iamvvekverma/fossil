from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from fossil.models import HoldPattern, PatternResult
from fossil.repo import run_git

PATTERNS = [
    re.compile(r"TODO:\s*remove after\s+(?P<condition>.+)", re.IGNORECASE),
    re.compile(r"FIXME:\s*delete when\s+(?P<condition>.+)", re.IGNORECASE),
    re.compile(
        r"keep(?:ing)? (?:this )?(?:around )?(?:for now|until\s+(?P<condition>.+))", re.IGNORECASE
    ),
    re.compile(r"\btemporary\b|\btemp code\b|\btemp fix\b", re.IGNORECASE),
    re.compile(r"\bDEPRECATED\b|@deprecated", re.IGNORECASE),
    re.compile(r"will be removed in\s+(?P<condition>.+)", re.IGNORECASE),
]


def detect_patterns(path: Path, repo_root: Path) -> PatternResult:
    result = PatternResult(detected=False)
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, line in enumerate(text.splitlines(), 1):
        for regex in PATTERNS:
            match = regex.search(line)
            if not match:
                continue
            condition = (match.groupdict().get("condition") or "").strip(" .#")
            kind, met, evidence = verify_condition(condition, repo_root)
            result.patterns.append(
                HoldPattern(
                    text=line.strip(),
                    line=line_no,
                    condition=condition or None,
                    condition_type=kind,
                    condition_met=met,
                    evidence=evidence,
                )
            )
    result.detected = bool(result.patterns)
    return result


def verify_condition(condition: str, repo_root: Path) -> tuple[str, bool | None, str]:
    if not condition:
        return "unverifiable", None, "No explicit condition found."
    pr = re.search(r"(?:PR|#)\s*(\d+)", condition, re.IGNORECASE)
    if pr:
        number = pr.group(1)
        log = run_git(
            repo_root, ["log", "--all", "--grep", f"#{number}", "--format=%H %s"], check=False
        )
        if log.stdout.strip():
            return "pr", True, f"Found commit message referencing #{number}."
        return "pr", None, f"PR #{number} requires remote API verification."
    version = re.search(r"\bv?(\d+\.\d+(?:\.\d+)?)\b", condition)
    if version:
        tags = run_git(repo_root, ["tag", "--list", f"*{version.group(1)}*"], check=False)
        if tags.stdout.strip():
            return "version", True, f"Matching git tag found: {tags.stdout.splitlines()[0]}."
        return "version", False, f"No git tag matched version {version.group(1)}."
    parsed = _parse_date(condition)
    if parsed:
        if parsed <= date.today():
            return "date", True, f"Date {parsed.isoformat()} has passed."
        return "date", False, f"Date {parsed.isoformat()} has not passed."
    return "unverifiable", None, f'Condition: UNVERIFIABLE — "{condition}"'


def _parse_date(value: str) -> date | None:
    for token in re.findall(r"\d{4}-\d{2}-\d{2}|\d{4}/\d{2}/\d{2}", value):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(token, fmt).date()
            except ValueError:
                pass
    return None
