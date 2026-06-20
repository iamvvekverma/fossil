from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Reference:
    path: str
    line: int
    kind: str
    text: str


@dataclass
class StaticAnalysisResult:
    language: str
    call_sites: int = 0
    import_references: int = 0
    dynamic_references: list[Reference] = field(default_factory=list)
    reflection_patterns: list[Reference] = field(default_factory=list)
    test_file_references: int = 0
    documentation_references: int = 0
    config_file_references: int = 0
    references: list[Reference] = field(default_factory=list)
    unknown_language: bool = False

    @property
    def main_code_references(self) -> int:
        return max(0, self.call_sites + self.import_references)


@dataclass
class CommitInfo:
    hash: str
    short_hash: str
    date: str
    author_name: str
    author_email: str
    message: str
    pr_number: int | None = None


@dataclass
class GitHistoryResult:
    head: str
    tracked: bool
    shallow: bool = False
    remote_url: str | None = None
    death_commit: CommitInfo | None = None
    original_author: CommitInfo | None = None
    last_modified: CommitInfo | None = None
    ambiguous_death: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class HoldPattern:
    text: str
    line: int
    condition: str | None
    condition_type: str
    condition_met: bool | None
    evidence: str


@dataclass
class PatternResult:
    detected: bool
    patterns: list[HoldPattern] = field(default_factory=list)


@dataclass
class ConfidenceSignal:
    name: str
    weight: int
    applied: bool
    reason: str


@dataclass
class ConfidenceResult:
    score: int
    label: str
    risk: str
    signals: list[ConfidenceSignal]


@dataclass
class ForensicResult:
    fossil_version: str
    target: str
    abs_path: str
    repo_root: str
    language: str
    dead: bool
    status: str
    static_analysis: StaticAnalysisResult
    git_history: GitHistoryResult
    temporary_hold: PatternResult
    confidence: ConfidenceResult | None
    suggested_action: str | None
    yolo_command: str | None
    analysis_duration_ms: int
    cached: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

