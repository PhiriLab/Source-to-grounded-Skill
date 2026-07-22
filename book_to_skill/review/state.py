"""Skill lifecycle states and the publication gate.

    draft -> security-cleared -> source-verified -> expert-reviewed -> published
                                                                        |
                                                                    deprecated

Transitions are forward-only (plus any state -> deprecated, and any state
back to draft on regeneration). The publication gate is deterministic and
mode-independent: no unresolved high/critical security findings, ledger
valid, citation markers resolvable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from book_to_skill.security.findings import FindingsReport, Severity


class SkillState(str, Enum):
    DRAFT = "draft"
    SECURITY_CLEARED = "security-cleared"
    SOURCE_VERIFIED = "source-verified"
    EXPERT_REVIEWED = "expert-reviewed"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


_ORDER = [
    SkillState.DRAFT,
    SkillState.SECURITY_CLEARED,
    SkillState.SOURCE_VERIFIED,
    SkillState.EXPERT_REVIEWED,
    SkillState.PUBLISHED,
]


def advance_state(current: SkillState, target: SkillState) -> SkillState:
    """Validate a transition; returns target or raises ValueError."""
    if target == SkillState.DEPRECATED:
        return target
    if target == SkillState.DRAFT:  # regeneration resets
        return target
    if current == SkillState.DEPRECATED:
        raise ValueError("a deprecated skill cannot advance; regenerate as draft")
    ci, ti = _ORDER.index(current), _ORDER.index(target)
    if ti != ci + 1:
        raise ValueError(
            f"invalid transition {current.value} -> {target.value}: "
            f"states advance one step at a time"
        )
    return target


@dataclass
class GateResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)

    def __bool__(self):
        return self.allowed


def publication_gate(
    state: SkillState,
    output_findings: FindingsReport,
    ledger_problems: list[str],
    citation_problems: list[str],
    reviewed_medium_findings: bool = False,
    require_expert_review: bool = True,
) -> GateResult:
    """Deterministic publish check. A model is never consulted here."""
    reasons: list[str] = []

    high = output_findings.at_or_above(Severity.HIGH)
    if high:
        reasons.append(
            f"{len(high)} unresolved high/critical security finding(s) in generated output"
        )
    medium = [f for f in output_findings.findings
              if f.risk == Severity.MEDIUM]
    if medium and not reviewed_medium_findings:
        reasons.append(
            f"{len(medium)} medium security finding(s) not yet reviewed"
        )
    if ledger_problems:
        reasons.append(f"claims ledger invalid: {len(ledger_problems)} problem(s)")
    if citation_problems:
        reasons.append(f"unresolvable citations: {len(citation_problems)}")
    required = SkillState.EXPERT_REVIEWED if require_expert_review else SkillState.SOURCE_VERIFIED
    if state == SkillState.DEPRECATED:
        reasons.append("skill is deprecated; regenerate as draft before publishing")
    elif _ORDER.index(state) < _ORDER.index(required):
        reasons.append(
            f"skill state is {state.value!r}; {required.value!r} required before publish"
        )
    return GateResult(allowed=not reasons, reasons=reasons)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
