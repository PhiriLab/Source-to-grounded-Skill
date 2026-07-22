"""JSONL claims ledger: the source of truth for generated content.

One claim per line, diff-friendly, append-oriented. Validation enforces the
governing rule: source-bound claims carry evidence; evidence spans carry
content hashes; long verbatim spans are flagged (copyright hygiene — the
skill should synthesise, not reproduce).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, Optional

from book_to_skill.provenance.ids import claim_id, span_hash
from book_to_skill.provenance.models import Claim, EvidenceSpan

# An evidence span longer than this is flagged: it stops being "supporting
# evidence" and starts being a reproduction of the source.
MAX_EVIDENCE_CHARS = 1200


class LedgerError(ValueError):
    pass


class ClaimsLedger:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self._claims: dict[str, Claim] = {}

    # -- construction --------------------------------------------------------

    def new_claim(self, **kwargs) -> Claim:
        """Create, hash, validate, and register the next claim."""
        cid = kwargs.pop("claim_id", None) or claim_id(len(self._claims) + 1)
        if cid in self._claims:
            raise LedgerError(f"duplicate claim id {cid}")
        claim = Claim(claim_id=cid, **kwargs)
        for span in claim.evidence:
            if not span.content_hash:
                span.content_hash = span_hash(span.text)
        self._claims[cid] = claim
        return claim

    def add(self, claim: Claim) -> None:
        if claim.claim_id in self._claims:
            raise LedgerError(f"duplicate claim id {claim.claim_id}")
        for span in claim.evidence:
            if not span.content_hash:
                span.content_hash = span_hash(span.text)
        self._claims[claim.claim_id] = claim

    # -- access --------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._claims)

    def __iter__(self) -> Iterator[Claim]:
        return iter(self._claims.values())

    def get(self, cid: str) -> Optional[Claim]:
        return self._claims.get(cid)

    # -- validation ----------------------------------------------------------

    def validate(self, source_texts: Optional[dict[str, str]] = None) -> list[str]:
        """Return a list of problems (empty = valid).

        With ``source_texts`` (source_id -> preserved original extraction),
        also verifies that each evidence span's offsets reproduce text whose
        content hash matches the recorded one — i.e. citations are not just
        present but *correct*.
        """
        problems: list[str] = []
        for claim in self:
            for i, span in enumerate(claim.evidence):
                if span.end_char <= span.start_char:
                    problems.append(f"{claim.claim_id}: evidence[{i}] empty offset range")
                if len(span.text) > MAX_EVIDENCE_CHARS:
                    problems.append(
                        f"{claim.claim_id}: evidence[{i}] is {len(span.text)} chars "
                        f"(> {MAX_EVIDENCE_CHARS}) — synthesise, don't reproduce"
                    )
                if span.content_hash != span_hash(span.text):
                    problems.append(f"{claim.claim_id}: evidence[{i}] hash mismatch")
                if source_texts is not None:
                    src = source_texts.get(span.source_id)
                    if src is None:
                        problems.append(
                            f"{claim.claim_id}: evidence[{i}] references unknown "
                            f"source {span.source_id}"
                        )
                    else:
                        actual = src[span.start_char:span.end_char]
                        if span_hash(actual) != span.content_hash:
                            problems.append(
                                f"{claim.claim_id}: evidence[{i}] offsets do not "
                                f"match recorded text in {span.source_id}"
                            )
            if claim.epistemic_status == "external_contextualisation" and claim.source_id:
                problems.append(
                    f"{claim.claim_id}: external contextualisation must not be "
                    f"attributed to a source"
                )
        return problems

    # -- change detection (fold-in / update) ---------------------------------

    def invalidated_by(self, source_texts: dict[str, str]) -> list[Claim]:
        """Claims whose evidence no longer matches the (new) source texts."""
        stale = []
        for claim in self:
            for span in claim.evidence:
                src = source_texts.get(span.source_id)
                if src is None or span_hash(src[span.start_char:span.end_char]) != span.content_hash:
                    stale.append(claim)
                    break
        return stale

    # -- persistence ---------------------------------------------------------

    def save(self, path: Optional[Path] = None) -> Path:
        path = Path(path) if path else self.path
        if path is None:
            raise LedgerError("no ledger path set")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for claim in self:
                fh.write(json.dumps(claim.to_dict(), ensure_ascii=False) + "\n")
        self.path = path
        return path

    @classmethod
    def load(cls, path: Path) -> "ClaimsLedger":
        ledger = cls(path)
        path = Path(path)
        if not path.exists():
            return ledger
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                ledger.add(Claim.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise LedgerError(f"{path}:{line_no}: {exc}") from exc
        return ledger
