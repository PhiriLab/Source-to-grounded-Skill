"""Structured security findings shared by all scanners."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}

# Category slugs are stable API: policy rules and tests key on them.
CATEGORIES = frozenset(
    {
        "indirect_prompt_injection",
        "hidden_unicode",
        "hidden_html",
        "encoded_content",
        "structure_forgery",
        "resource_abuse",
        "path_traversal",
        "shell_execution",
        "network_access",
        "credential_access",
        "destructive_file_operation",
        "agent_role_redefinition",
        "disclosure_suppression",
        "citation_suppression",
        "unverified_external_url",
        "identifier_exposure",
        "missing_provenance",
    }
)

RECOMMENDED_ACTIONS = ("record", "review", "analysis_only", "stop", "quarantine")


@dataclass
class SecurityFinding:
    risk: Severity
    category: str
    source_id: str  # source/file identifier, or generated file path for output scans
    evidence: str  # short excerpt; never the whole document
    recommended_action: str
    location: dict = field(default_factory=dict)  # e.g. {"line": 12, "start_char": 9283, "end_char": 9512, "page": 143}
    detector: str = ""
    note: str = ""

    def __post_init__(self):
        if isinstance(self.risk, str):
            self.risk = Severity(self.risk)
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown finding category: {self.category!r}")
        if self.recommended_action not in RECOMMENDED_ACTIONS:
            raise ValueError(f"unknown recommended action: {self.recommended_action!r}")
        # Evidence is capped so findings files never become a second copy of
        # the (possibly restricted) source.
        if len(self.evidence) > 300:
            self.evidence = self.evidence[:297] + "..."

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk"] = self.risk.value
        return d


@dataclass
class FindingsReport:
    findings: list[SecurityFinding] = field(default_factory=list)

    def add(self, finding: SecurityFinding) -> None:
        self.findings.append(finding)

    def extend(self, other: "FindingsReport") -> None:
        self.findings.extend(other.findings)

    @property
    def max_severity(self) -> Optional[Severity]:
        if not self.findings:
            return None
        return max((f.risk for f in self.findings), key=lambda s: s.rank)

    def at_or_above(self, severity: Severity) -> list[SecurityFinding]:
        return [f for f in self.findings if f.risk.rank >= severity.rank]

    def by_category(self, category: str) -> list[SecurityFinding]:
        return [f for f in self.findings if f.category == category]

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for f in self.findings:
                fh.write(json.dumps(f.to_dict(), ensure_ascii=False) + "\n")

    @classmethod
    def read_jsonl(cls, path: Path) -> "FindingsReport":
        report = cls()
        if not path.exists():
            return report
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            report.add(SecurityFinding(**d))
        return report
