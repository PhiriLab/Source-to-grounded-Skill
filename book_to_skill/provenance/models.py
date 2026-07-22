"""Stable provenance entities.

All entities serialise to plain dicts (JSON/JSONL friendly) and are keyed by
stable, prefix-typed IDs (see ids.py). The claims ledger is the source of
truth: generated Markdown is downstream of it and must not introduce
substantive content the ledger doesn't carry.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

# Epistemic statuses a claim may carry. Order matters for review priority
# (later entries are the more editorially loaded ones).
EPISTEMIC_STATUSES = (
    "direct_quotation",
    "close_paraphrase",
    "author_position",
    "empirical_finding",
    "methodological_recommendation",
    "clinical_recommendation",
    "cross_source_synthesis",
    "editorial_inference",
    "external_contextualisation",
    "reviewer_annotation",
    "contested_claim",
    "uncertainty_or_limitation",
)

CLAIM_TYPES = (
    "definition",
    "author_argument",
    "empirical_finding",
    "clinical_recommendation",
    "methodological_rule",
    "theoretical_proposition",
    "historical_claim",
    "ethical_position",
    "case_example",
    "critique",
    "limitation",
    "uncertainty",
    "editorial_synthesis",
)

# Statuses that require at least one supporting evidence span. External
# contextualisation and reviewer annotations are the only statuses allowed
# to stand without source support — and they must be visibly labelled.
SOURCE_BOUND_STATUSES = frozenset(EPISTEMIC_STATUSES) - {
    "external_contextualisation",
    "reviewer_annotation",
}

REVIEW_STATUSES = ("unreviewed", "approved", "rejected", "annotated")

PRIVACY_CLASSES = (
    "public",
    "copyrighted-private",
    "institutional-confidential",
    "clinical-restricted",
)

SKILL_STATES = (
    "draft",
    "security-cleared",
    "source-verified",
    "expert-reviewed",
    "published",
    "deprecated",
)


def _check(value: str, allowed, label: str) -> str:
    if value not in allowed:
        raise ValueError(f"unknown {label}: {value!r} (allowed: {', '.join(allowed)})")
    return value


@dataclass
class Source:
    source_id: str  # e.g. "SRC-a1b2c3d4"
    title: str
    path: str
    sha256: str
    authors: list[str] = field(default_factory=list)
    edition: str = ""
    year: Optional[int] = None
    bibliographic_id: str = ""  # DOI / ISBN / registry id where available
    privacy: str = "copyrighted-private"
    extraction_tool: str = ""
    extraction_tool_version: str = ""
    extraction_timestamp: str = ""
    citation_key: str = ""  # short human key used in [SRC:...] markers, e.g. "BOOK1"

    def __post_init__(self):
        _check(self.privacy, PRIVACY_CLASSES, "privacy classification")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocumentSection:
    """A node in the hierarchical structure: part/chapter/section/etc.

    Anchored by character offsets into the preserved original extraction of
    its source, so every child span is addressable without a sentence tree.
    """

    section_id: str  # e.g. "SEC-BOOK1-ch04"
    source_id: str
    kind: str  # "part" | "chapter" | "section" | "subsection" | "table" | "figure" | "case"
    title: str
    start_char: int
    end_char: int
    parent_id: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    citation_label: str = ""  # e.g. "CH04" — used in markers

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvidenceSpan:
    source_id: str
    start_char: int
    end_char: int
    text: str  # the supporting passage (bounded; see ledger validation)
    section_id: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    content_hash: str = ""  # sha256 of text; set by ledger on add

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Claim:
    claim_id: str  # "CLM-000481"
    source_id: str  # primary source ("" only for external/reviewer statuses)
    claim_type: str
    epistemic_status: str
    paraphrase: str  # the generated representation used downstream
    evidence: list[EvidenceSpan] = field(default_factory=list)
    section_id: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    confidence: float = 1.0
    review_status: str = "unreviewed"
    review_note: str = ""
    related_claims: list[str] = field(default_factory=list)  # e.g. contradiction partners
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        _check(self.claim_type, CLAIM_TYPES, "claim type")
        _check(self.epistemic_status, EPISTEMIC_STATUSES, "epistemic status")
        _check(self.review_status, REVIEW_STATUSES, "review status")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of range: {self.confidence}")
        if self.epistemic_status in SOURCE_BOUND_STATUSES and not self.evidence:
            raise ValueError(
                f"claim {self.claim_id}: epistemic status "
                f"{self.epistemic_status!r} requires at least one evidence span"
            )
        if not self.paraphrase.strip():
            raise ValueError(f"claim {self.claim_id}: empty paraphrase")

    @property
    def is_source_bound(self) -> bool:
        return self.epistemic_status in SOURCE_BOUND_STATUSES

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Claim":
        d = dict(d)
        d["evidence"] = [EvidenceSpan(**e) for e in d.get("evidence", [])]
        return cls(**d)


@dataclass
class ReviewDecision:
    claim_id: str
    decision: str  # "approved" | "rejected" | "annotated"
    reviewer: str
    timestamp: str
    reason: str = ""
    annotation: str = ""
    evidence_hash: str = ""  # content hash of the supporting span at decision
    # time; a changed hash invalidates the decision

    def __post_init__(self):
        if self.decision not in ("approved", "rejected", "annotated"):
            raise ValueError(f"unknown decision: {self.decision!r}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GenerationManifest:
    skill_id: str
    state: str = "draft"
    profile: str = "scholarly-book"
    privacy: str = "copyrighted-private"
    world_knowledge: str = "off"  # off | labelled | unrestricted
    citation_mode: str = "claim"
    security_mode: str = "standard"
    generator_version: str = ""
    model: str = ""
    created_at: str = ""
    sources: list[dict] = field(default_factory=list)  # Source.to_dict()
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    state_history: list[dict] = field(default_factory=list)

    def __post_init__(self):
        _check(self.state, SKILL_STATES, "skill state")
        _check(self.privacy, PRIVACY_CLASSES, "privacy classification")
        if self.world_knowledge not in ("off", "labelled", "unrestricted"):
            raise ValueError(f"unknown world-knowledge mode: {self.world_knowledge!r}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GenerationManifest":
        return cls(**d)
