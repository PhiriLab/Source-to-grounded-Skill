"""Citation marker grammar for generated Markdown.

Markers are inline, resolvable, and stable:

    [SRC:BOOK1:CH04:P87-91]        source : section : page range
    [SRC:BOOK1:CH04]               page unknown
    [SRC:BOOK1:CH04:C9283-9512]    character-offset locator
    [CLM:CLM-000481]               reference to a ledger claim

`citation_coverage` measures the fraction of substantive paragraphs that
carry at least one marker — a release-gated metric (evaluation/metrics.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

MARKER_RE = re.compile(
    r"\[(?:SRC:(?P<source>[A-Za-z0-9_-]+)"
    r"(?::(?P<section>[A-Za-z0-9_-]+))?"
    r"(?::(?P<locator>[PC]\d+(?:-\d+)?))?"
    r"|CLM:(?P<claim>CLM-\d{6}))\]"
)

# Paragraphs that don't need citations: headings, tables, list scaffolding,
# blockquote attribution lines, markers-only lines, front-matter, short
# navigational text.
_EXEMPT = re.compile(
    r"^\s*(?:#{1,6}\s|\||[-*+]\s*$|>\s*$|---|```|\[SRC:|\[CLM:|<!--)"
)


@dataclass(frozen=True)
class CitationMarker:
    raw: str
    source: Optional[str]
    section: Optional[str]
    locator: Optional[str]
    claim: Optional[str]

    @property
    def page_range(self) -> Optional[tuple[int, int]]:
        if self.locator and self.locator.startswith("P"):
            parts = self.locator[1:].split("-")
            start = int(parts[0])
            return (start, int(parts[1]) if len(parts) > 1 else start)
        return None

    @property
    def char_range(self) -> Optional[tuple[int, int]]:
        if self.locator and self.locator.startswith("C"):
            parts = self.locator[1:].split("-")
            start = int(parts[0])
            return (start, int(parts[1]) if len(parts) > 1 else start)
        return None


def parse_markers(text: str) -> list[CitationMarker]:
    return [
        CitationMarker(
            raw=m.group(0),
            source=m.group("source"),
            section=m.group("section"),
            locator=m.group("locator"),
            claim=m.group("claim"),
        )
        for m in MARKER_RE.finditer(text)
    ]


def _substantive_paragraphs(markdown: str) -> list[str]:
    paras = []
    for block in re.split(r"\n\s*\n", markdown):
        block = block.strip()
        if not block or len(block) < 80:
            continue
        first_line = block.splitlines()[0]
        if _EXEMPT.match(first_line):
            continue
        paras.append(block)
    return paras


def citation_coverage(markdown: str) -> tuple[float, list[str]]:
    """(coverage ratio, uncited substantive paragraphs)."""
    paras = _substantive_paragraphs(markdown)
    if not paras:
        return 1.0, []
    uncited = [p for p in paras if not MARKER_RE.search(p)]
    return 1.0 - len(uncited) / len(paras), uncited


def validate_markers(
    markdown: str,
    known_sources: set[str],
    known_sections: Optional[set[str]] = None,
    known_claims: Optional[set[str]] = None,
) -> list[str]:
    """Check that every marker resolves to a registered entity."""
    problems = []
    for m in parse_markers(markdown):
        if m.claim is not None:
            if known_claims is not None and m.claim not in known_claims:
                problems.append(f"unresolvable claim marker {m.raw}")
            continue
        if m.source not in known_sources:
            problems.append(f"unresolvable source marker {m.raw}")
        elif m.section and known_sections is not None:
            if f"{m.source}:{m.section}" not in known_sections:
                problems.append(f"unresolvable section in marker {m.raw}")
    return problems
