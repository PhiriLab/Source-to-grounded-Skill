"""Reviewer decisions: approve / reject / annotate, persisted as JSONL.

Decisions are keyed to the content hash of the claim's supporting evidence
at decision time. On regeneration, a decision re-applies only if the
evidence hash still matches — a materially changed passage invalidates the
old decision and returns the claim to `unreviewed` (docs/REVIEW_GUIDE.md).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from book_to_skill.provenance.ledger import ClaimsLedger
from book_to_skill.provenance.models import Claim, ReviewDecision
from book_to_skill.review.state import utc_now


def _claim_evidence_hash(claim: Claim) -> str:
    return "+".join(span.content_hash for span in claim.evidence)


class DecisionStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._decisions: dict[str, ReviewDecision] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = ReviewDecision(**json.loads(line))
                    self._decisions[d.claim_id] = d  # last decision wins

    def _record(self, decision: ReviewDecision) -> None:
        self._decisions[decision.claim_id] = decision
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(decision.to_dict(), ensure_ascii=False) + "\n")

    def approve(self, claim: Claim, reviewer: str, reason: str = "") -> ReviewDecision:
        d = ReviewDecision(claim_id=claim.claim_id, decision="approved",
                           reviewer=reviewer, timestamp=utc_now(), reason=reason,
                           evidence_hash=_claim_evidence_hash(claim))
        claim.review_status = "approved"
        claim.review_note = reason
        self._record(d)
        return d

    def reject(self, claim: Claim, reviewer: str, reason: str) -> ReviewDecision:
        if not reason.strip():
            raise ValueError("rejection requires a reason")
        d = ReviewDecision(claim_id=claim.claim_id, decision="rejected",
                           reviewer=reviewer, timestamp=utc_now(), reason=reason,
                           evidence_hash=_claim_evidence_hash(claim))
        claim.review_status = "rejected"
        claim.review_note = reason
        self._record(d)
        return d

    def annotate(self, claim: Claim, reviewer: str, annotation: str) -> ReviewDecision:
        d = ReviewDecision(claim_id=claim.claim_id, decision="annotated",
                           reviewer=reviewer, timestamp=utc_now(),
                           annotation=annotation,
                           evidence_hash=_claim_evidence_hash(claim))
        if claim.review_status == "unreviewed":
            claim.review_status = "annotated"
        claim.review_note = annotation
        self._record(d)
        return d

    def get(self, claim_id: str) -> Optional[ReviewDecision]:
        return self._decisions.get(claim_id)

    def reapply(self, ledger: ClaimsLedger) -> dict:
        """Re-apply stored decisions to a (re)generated ledger.

        Returns {"applied": [...], "invalidated": [...], "orphaned": [...]}.
        A decision applies only when the claim still exists and its evidence
        hash is unchanged; otherwise the claim stays `unreviewed`.
        """
        applied, invalidated, orphaned = [], [], []
        for cid, decision in self._decisions.items():
            claim = ledger.get(cid)
            if claim is None:
                orphaned.append(cid)
                continue
            if _claim_evidence_hash(claim) == decision.evidence_hash:
                claim.review_status = (
                    decision.decision if decision.decision != "annotated"
                    else ("annotated" if claim.review_status == "unreviewed"
                          else claim.review_status)
                )
                claim.review_note = decision.reason or decision.annotation
                applied.append(cid)
            else:
                claim.review_status = "unreviewed"
                invalidated.append(cid)
        return {"applied": applied, "invalidated": invalidated, "orphaned": orphaned}
