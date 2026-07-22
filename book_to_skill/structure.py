"""Hierarchical source representation.

Builds DocumentSection nodes (with character offsets into the preserved
extraction) from, in priority order:

1. a user-supplied YAML structure map (authoritative when given), or
2. detected chapter headings (reusing the upstream multilingual detector).

A structure map wins outright because for unconventionally organised books
manual structure beats generic detection (docs/FORK_ARCHITECTURE_PLAN.md).

Structure map format:

    structure:
      - title: Part I
        children:
          - title: The cultural encounter
            start_page: 13
            end_page: 38
            match: "THE CULTURAL ENCOUNTER"   # optional literal to locate

Offsets for map entries are located by searching for `match` (or the title)
in the text; entries that cannot be located are reported, not guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from book_to_skill.provenance.models import DocumentSection
from book_to_skill.utils import _chapter_number

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class StructureResult:
    sections: list[DocumentSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def detect_sections(text: str, source_id: str, citation_key: str) -> StructureResult:
    """Chapter-level sections from detected headings, with char offsets."""
    result = StructureResult()
    offset = 0
    boundaries: list[tuple[int, int, str]] = []  # (start_char, number, title line)
    seen: set[int] = set()
    for line in text.splitlines(keepends=True):
        num = _chapter_number(line)
        if num is not None and num not in seen:
            seen.add(num)
            boundaries.append((offset, num, line.strip()))
        offset += len(line)
    if not boundaries:
        result.warnings.append(
            f"{citation_key}: no chapter headings detected — provide a "
            f"structure map (--structure-map) for reliable sectioning"
        )
        return result
    for i, (start, num, title) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        label = f"CH{num:02d}"
        result.sections.append(DocumentSection(
            section_id=f"SEC-{citation_key}-{label}",
            source_id=source_id,
            kind="chapter",
            title=title,
            start_char=start,
            end_char=end,
            citation_label=label,
        ))
    return result


def _walk_map(entries, text, source_id, citation_key, parent_id, result, counter):
    for entry in entries:
        title = str(entry.get("title", "")).strip()
        if not title:
            result.warnings.append(f"{citation_key}: structure-map entry without title skipped")
            continue
        needle = str(entry.get("match", title))
        pos = text.find(needle)
        counter[0] += 1
        label = f"S{counter[0]:03d}"
        if pos < 0:
            result.warnings.append(
                f"{citation_key}: could not locate {title!r} in extracted text"
            )
            continue
        section = DocumentSection(
            section_id=f"SEC-{citation_key}-{label}",
            source_id=source_id,
            kind=str(entry.get("kind", "chapter")),
            title=title,
            start_char=pos,
            end_char=len(text),  # tightened below
            parent_id=parent_id,
            page_start=entry.get("start_page"),
            page_end=entry.get("end_page"),
            citation_label=label,
        )
        result.sections.append(section)
        _walk_map(entry.get("children", []), text, source_id, citation_key,
                  section.section_id, result, counter)


def sections_from_map(map_text: str, text: str, source_id: str, citation_key: str) -> StructureResult:
    if yaml is None:
        raise RuntimeError("PyYAML is required for structure maps")
    result = StructureResult()
    data = yaml.safe_load(map_text) or {}
    _walk_map(data.get("structure", []), text, source_id, citation_key,
              None, result, counter=[0])
    # Tighten end offsets: each section ends where the next sibling-or-later
    # section at any level starts.
    ordered = sorted(result.sections, key=lambda s: s.start_char)
    for i, sec in enumerate(ordered):
        later = [s.start_char for s in ordered[i + 1:] if s.start_char > sec.start_char
                 and s.parent_id != sec.section_id]
        if later:
            sec.end_char = min(later)
    return result
