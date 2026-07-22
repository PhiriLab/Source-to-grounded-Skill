"""Adjudication of source-scan security findings.

Source findings (`security/source_findings.jsonl`) are immutable audit
records — never edited or deleted. A reviewer can *adjudicate* a finding
(mark it `accepted` or a `false_positive`, with a reason); the decision is
appended to `security/finding_adjudications.jsonl`, keyed to a stable
fingerprint so it survives re-scanning of the same source.

This closes the workflow gap where a benign source finding (e.g. an
injection false-positive on procedural text) could be recorded but never
formally cleared — `annotate` only applies to claims.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

DECISIONS = ("accepted", "false_positive")


def finding_fingerprint(finding: dict) -> str:
    """Stable id for a finding from its detector, category, source and
    location — so an adjudication re-matches after re-scanning."""
    loc = finding.get("location", {}) or {}
    key = "|".join(str(x) for x in (
        finding.get("detector", ""),
        finding.get("category", ""),
        finding.get("source_id", ""),
        loc.get("start_char", ""),
        loc.get("end_char", ""),
        loc.get("offset", ""),
    ))
    return "FND-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


@dataclass
class FindingAdjudication:
    fingerprint: str
    finding_index: int
    decision: str
    reviewer: str
    reason: str
    timestamp: str
    detector: str = ""
    category: str = ""

    def __post_init__(self):
        if self.decision not in DECISIONS:
            raise ValueError(f"unknown decision {self.decision!r} (accepted|false_positive)")
        if not self.reason.strip():
            raise ValueError("adjudication requires a reason")

    def to_dict(self) -> dict:
        return asdict(self)


class AdjudicationStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._by_fp: dict[str, FindingAdjudication] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    d = json.loads(line)
                    self._by_fp[d["fingerprint"]] = FindingAdjudication(**d)

    def record(self, adj: FindingAdjudication) -> None:
        self._by_fp[adj.fingerprint] = adj  # last decision wins
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(adj.to_dict(), ensure_ascii=False) + "\n")

    def get(self, fingerprint: str) -> Optional[FindingAdjudication]:
        return self._by_fp.get(fingerprint)

    def decision_map(self) -> dict[str, str]:
        return {fp: a.decision for fp, a in self._by_fp.items()}

    def __len__(self) -> int:
        return len(self._by_fp)
