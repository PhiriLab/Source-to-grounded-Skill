"""Risk policy: maps scan findings to pipeline decisions.

Default policy (docs/FORK_ARCHITECTURE_PLAN.md):
    low      -> continue, record
    medium   -> continue only in analysis mode; blocks publication until reviewed
    high     -> stop before generation
    critical -> quarantine the source

Security modes tighten or (for `permissive`) loosen the generation gate, but
no mode ever allows *publication* with unresolved high/critical findings —
publish gating is not mode-dependent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from book_to_skill.security.findings import FindingsReport, Severity


class GateDecision(str, Enum):
    PROCEED = "proceed"
    ANALYSIS_ONLY = "analysis_only"
    STOP = "stop"
    QUARANTINE = "quarantine"


# Resource limits applied at extraction time (T1 resource abuse).
MAX_SOURCE_SIZE_MB = 500
MAX_PAGES = 10_000
MAX_TOKENS = 5_000_000
MAX_DECOMPRESSED_ZIP_MB = 2_000  # EPUB/DOCX payload after decompression
MAX_ZIP_RATIO = 200  # decompressed/compressed ratio beyond which we refuse


@dataclass(frozen=True)
class SecurityPolicy:
    """Thresholds keyed by security mode (--security strict|standard|permissive)."""

    mode: str = "standard"

    # Lowest severity that forces analysis-only / stop / quarantine during
    # source scanning. Publication gating is fixed and mode-independent.
    @property
    def analysis_only_at(self) -> Severity:
        return {"strict": Severity.LOW, "standard": Severity.MEDIUM,
                "permissive": Severity.HIGH}[self.mode]

    @property
    def stop_at(self) -> Severity:
        return {"strict": Severity.MEDIUM, "standard": Severity.HIGH,
                "permissive": Severity.CRITICAL}[self.mode]

    @property
    def quarantine_at(self) -> Severity:
        return Severity.CRITICAL  # all modes

    def __post_init__(self):
        if self.mode not in ("strict", "standard", "permissive"):
            raise ValueError(f"unknown security mode: {self.mode!r}")


def evaluate_findings(report: FindingsReport, policy: SecurityPolicy = SecurityPolicy()) -> GateDecision:
    """Decide how the pipeline may proceed after a *source* scan."""
    top = report.max_severity
    if top is None:
        return GateDecision.PROCEED
    if top.rank >= policy.quarantine_at.rank:
        return GateDecision.QUARANTINE
    if top.rank >= policy.stop_at.rank:
        return GateDecision.STOP
    if top.rank >= policy.analysis_only_at.rank:
        return GateDecision.ANALYSIS_ONLY
    return GateDecision.PROCEED


def publication_blockers(report: FindingsReport) -> list:
    """Findings that block publication regardless of security mode.

    High/critical always block. Medium blocks until explicitly reviewed
    (the review workflow clears them by recording a decision, not by
    deleting the finding).
    """
    return report.at_or_above(Severity.MEDIUM)
