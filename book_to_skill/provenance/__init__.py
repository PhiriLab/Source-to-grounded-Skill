"""Provenance model: every substantive generated claim remains traceable to
an identifiable source passage (docs/PROVENANCE_SPEC.md).
"""

from book_to_skill.provenance.models import (
    Source,
    DocumentSection,
    EvidenceSpan,
    Claim,
    ReviewDecision,
    GenerationManifest,
    EPISTEMIC_STATUSES,
    CLAIM_TYPES,
)
from book_to_skill.provenance.ids import claim_id, source_id_for, span_hash
from book_to_skill.provenance.ledger import ClaimsLedger
from book_to_skill.provenance.citations import (
    CitationMarker,
    parse_markers,
    citation_coverage,
)
from book_to_skill.provenance.trace import trace_claim

__all__ = [
    "Source",
    "DocumentSection",
    "EvidenceSpan",
    "Claim",
    "ReviewDecision",
    "GenerationManifest",
    "EPISTEMIC_STATUSES",
    "CLAIM_TYPES",
    "claim_id",
    "source_id_for",
    "span_hash",
    "ClaimsLedger",
    "CitationMarker",
    "parse_markers",
    "citation_coverage",
    "trace_claim",
]
