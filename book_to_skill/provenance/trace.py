"""Trace a claim from a generated skill back to its source passage(s)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from book_to_skill.provenance.ledger import ClaimsLedger


def trace_claim(
    staged_skill_dir: Path,
    claim_id: str,
    source_texts: Optional[dict[str, str]] = None,
) -> dict:
    """Resolve one claim: bibliographic context, evidence spans, review state,
    and which generated files cite it.

    ``source_texts`` (source_id -> preserved original extraction) enables
    verbatim passage checks; without it the recorded span text is returned.
    """
    staged = Path(staged_skill_dir)
    ledger = ClaimsLedger.load(staged / "provenance" / "claims.jsonl")
    claim = ledger.get(claim_id)
    if claim is None:
        raise KeyError(f"claim {claim_id} not found in {staged}")

    sources_path = staged / "provenance" / "sources.json"
    sources = {}
    if sources_path.exists():
        for s in json.loads(sources_path.read_text(encoding="utf-8")):
            sources[s["source_id"]] = s

    citing_files = []
    for md in sorted(staged.rglob("*.md")):
        try:
            if claim_id in md.read_text(encoding="utf-8"):
                citing_files.append(str(md.relative_to(staged)))
        except OSError:
            continue

    evidence = []
    for span in claim.evidence:
        entry = span.to_dict()
        if source_texts is not None and span.source_id in source_texts:
            actual = source_texts[span.source_id][span.start_char:span.end_char]
            entry["current_source_text"] = actual
            entry["matches_recorded"] = " ".join(actual.split()) == " ".join(span.text.split())
        evidence.append(entry)

    src_meta = sources.get(claim.source_id, {})
    return {
        "claim": claim.to_dict(),
        "source": {
            k: src_meta.get(k)
            for k in ("title", "authors", "edition", "year", "bibliographic_id", "citation_key")
        } if src_meta else None,
        "evidence": evidence,
        "review_status": claim.review_status,
        "cited_in": citing_files,
    }
