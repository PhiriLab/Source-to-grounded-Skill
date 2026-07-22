"""Stable, prefix-typed identifiers.

Source and section IDs are content-derived (hash-based) so regeneration over
unchanged sources yields identical IDs — which is what lets reviewer
decisions survive regeneration. Claim IDs are ledger-sequential with a
content-derived suffix check kept in the ledger itself.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def span_hash(text: str) -> str:
    """Content hash of an evidence span (whitespace-normalised so line
    rewrapping between extractions doesn't invalidate review decisions)."""
    normalised = " ".join(text.split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def source_id_for(sha256: str) -> str:
    return f"SRC-{sha256[:12]}"


def section_id_for(source_citation_key: str, label: str) -> str:
    return f"SEC-{source_citation_key}-{label}"


def claim_id(n: int) -> str:
    return f"CLM-{n:06d}"
