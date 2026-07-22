"""REVIEW.md generation: what a human reviewer must look at, ranked."""

from __future__ import annotations

from book_to_skill.provenance.integrity import check_ledger_integrity
from book_to_skill.provenance.ledger import ClaimsLedger
from book_to_skill.security.findings import FindingsReport, Severity

LOW_CONFIDENCE = 0.7

_HIGH_IMPACT_STATUSES = (
    "clinical_recommendation",
    "cross_source_synthesis",
    "editorial_inference",
    "contested_claim",
)


def _line(claim) -> str:
    pages = ""
    if claim.page_start:
        pages = f", p.{claim.page_start}" + (f"-{claim.page_end}" if claim.page_end else "")
    return (f"- **{claim.claim_id}** ({claim.epistemic_status}"
            f"{pages}, confidence {claim.confidence:.2f}) — {claim.paraphrase}")


def build_review_packet(
    ledger: ClaimsLedger,
    source_findings: FindingsReport,
    output_findings: FindingsReport,
    ledger_problems: list[str],
    citation_problems: list[str],
    uncited_paragraphs: list[str],
    extraction_warnings: list[str] | None = None,
) -> str:
    integrity_flags = check_ledger_integrity(ledger)
    sections: list[str] = ["# Review packet", ""]

    def add(title: str, lines: list[str], empty: str = "None.") -> None:
        sections.append(f"## {title}")
        sections.extend(lines if lines else [empty])
        sections.append("")

    add("High-impact claims (clinical, synthesis, inference, contested)", [
        _line(c) for c in ledger
        if c.epistemic_status in _HIGH_IMPACT_STATUSES or c.claim_type == "clinical_recommendation"
    ])
    add("Low-confidence claims", [
        _line(c) for c in ledger if c.confidence < LOW_CONFIDENCE
    ])
    add("Possible causal overstatement / lost qualifications", [
        f"- **{f.claim_id}**: {f.check} — {f.detail}"
        for f in integrity_flags if f.check in ("causal_or_scope_inflation", "qualification_loss")
    ])
    add("Other integrity flags", [
        f"- **{f.claim_id}**: {f.check} — {f.detail}"
        for f in integrity_flags if f.check not in ("causal_or_scope_inflation", "qualification_loss")
    ])
    add("Contradictions preserved (verify none were harmonised away)", [
        _line(c) for c in ledger if c.epistemic_status == "contested_claim"
    ], empty="No contested claims recorded — confirm the sources genuinely contain none.")
    add("Security findings (source scan)", [
        f"- [{f.risk.value}] {f.category} @ {f.source_id} {f.location}: {f.evidence}"
        for f in source_findings.at_or_above(Severity.LOW)
    ])
    add("Security findings (generated output)", [
        f"- [{f.risk.value}] {f.category} @ {f.source_id} {f.location}: {f.evidence}"
        for f in output_findings.at_or_above(Severity.LOW)
    ])
    add("Ledger validation problems", [f"- {p}" for p in ledger_problems])
    add("Unresolvable citations", [f"- {p}" for p in citation_problems])
    add("Uncited substantive paragraphs", [
        f"- {p[:160]}…" if len(p) > 160 else f"- {p}" for p in uncited_paragraphs
    ])
    add("Extraction warnings", [f"- {w}" for w in (extraction_warnings or [])])

    unreviewed = sum(1 for c in ledger if c.review_status == "unreviewed")
    sections.append("## Summary")
    sections.append(f"- Claims: {len(ledger)} total, {unreviewed} unreviewed")
    sections.append(f"- Integrity flags: {len(integrity_flags)}")
    sections.append(
        f"- Security: {len(source_findings.findings)} source finding(s), "
        f"{len(output_findings.findings)} output finding(s)"
    )
    sections.append("")
    return "\n".join(sections)
