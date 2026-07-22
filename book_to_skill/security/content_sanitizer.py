"""Unicode and hidden-content sanitisation for extracted source text.

Produces a sanitised *analysis copy* plus a transformation log; the original
text is never modified or discarded (docs/THREAT_MODEL.md, T1). Detection of
suspicious-but-ambiguous content (encoded blobs, HTML comments) is reported
as findings without altering the text.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from book_to_skill.security.findings import FindingsReport, SecurityFinding, Severity

# Bidirectional control characters: legitimate in RTL typography, but the
# override/isolate forms are the classic vehicle for "trojan source" text
# reordering. All are removed from the analysis copy and logged.
_BIDI_CONTROLS = {
    "\u202a": "LRE", "\u202b": "RLE", "\u202c": "PDF", "\u202d": "LRO",
    "\u202e": "RLO", "\u2066": "LRI", "\u2067": "RLI", "\u2068": "FSI",
    "\u2069": "PDI",
}
# The override/isolate forms specifically are what reorder rendered text.
_BIDI_HIGH_RISK = {"\u202d", "\u202e", "\u2066", "\u2067", "\u2068"}

# Zero-width and invisible characters used to hide text runs or split
# detector keywords.
_INVISIBLE = {
    "\u200b": "ZWSP", "\u200c": "ZWNJ", "\u200d": "ZWJ", "\u2060": "WJ",
    "\ufeff": "BOM/ZWNBSP", "\u00ad": "SHY", "\u180e": "MVS",
}

_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
# Inline CSS that renders text invisible (survives some HTML->text extractors).
_HIDDEN_CSS = re.compile(
    r"""style\s*=\s*["'][^"']*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|color\s*:\s*(?:#fff\b|#ffffff|white)\s*;?\s*background(?:-color)?\s*:\s*(?:#fff\b|#ffffff|white))""",
    re.IGNORECASE,
)
# Long runs of Base64-ish or hex content embedded in prose. Thresholds are
# high enough that DOIs, hashes quoted in a methods section, etc. don't trip.
_BASE64_BLOB = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{120,}={0,2}(?![A-Za-z0-9+/=])")
_HEX_BLOB = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[ :]?){60,}(?![0-9A-Fa-f])")


@dataclass
class SanitizationResult:
    original_text: str
    sanitized_text: str
    normalizations: list[dict] = field(default_factory=list)
    findings: FindingsReport = field(default_factory=FindingsReport)

    @property
    def changed(self) -> bool:
        return bool(self.normalizations)

    def log_dict(self, source_id: str) -> dict:
        return {"source_id": source_id, "normalizations": self.normalizations}


def _record(result: SanitizationResult, kind: str, offset: int, codepoint: str) -> None:
    result.normalizations.append(
        {"type": kind, "offset": offset, "original_codepoint": f"U+{ord(codepoint):04X}"}
    )


def sanitize_text(text: str, source_id: str = "source") -> SanitizationResult:
    """Return a sanitised analysis copy of ``text`` plus findings and a log.

    Offsets in the transformation log refer to positions in the NFC-normalised
    text (recorded before any removal), so the log replays deterministically.
    """
    findings = FindingsReport()

    nfc = unicodedata.normalize("NFC", text)
    result = SanitizationResult(original_text=text, sanitized_text=nfc, findings=findings)
    if nfc != text:
        result.normalizations.append({"type": "unicode_nfc_normalization", "offset": 0,
                                      "original_codepoint": None})

    # Character-level pass: strip bidi controls and invisibles, log each.
    out_chars: list[str] = []
    invisible_run = 0
    for i, ch in enumerate(nfc):
        if ch in _BIDI_CONTROLS:
            _record(result, "removed_bidi_control", i, ch)
            findings.add(SecurityFinding(
                risk=Severity.HIGH if ch in _BIDI_HIGH_RISK else Severity.MEDIUM,
                category="hidden_unicode",
                source_id=source_id,
                evidence=f"bidirectional control {_BIDI_CONTROLS[ch]} (U+{ord(ch):04X})",
                recommended_action="review",
                location={"offset": i},
                detector="content_sanitizer.bidi",
            ))
            continue
        if ch in _INVISIBLE:
            _record(result, "removed_invisible_character", i, ch)
            invisible_run += 1
            continue
        # Other C-category controls (excluding whitespace) are dropped quietly
        # but logged — common PDF-extraction artifacts, not per-char findings.
        if unicodedata.category(ch) == "Cf":
            _record(result, "removed_format_character", i, ch)
            continue
        out_chars.append(ch)
    result.sanitized_text = "".join(out_chars)

    if invisible_run:
        findings.add(SecurityFinding(
            risk=Severity.MEDIUM if invisible_run >= 5 else Severity.LOW,
            category="hidden_unicode",
            source_id=source_id,
            evidence=f"{invisible_run} zero-width/invisible character(s) removed",
            recommended_action="review" if invisible_run >= 5 else "record",
            detector="content_sanitizer.invisible",
        ))

    # Content-level detections: report, do not rewrite.
    for m in _HTML_COMMENT.finditer(nfc):
        body = m.group(1).strip()
        if body:
            findings.add(SecurityFinding(
                risk=Severity.MEDIUM,
                category="hidden_html",
                source_id=source_id,
                evidence=body[:200],
                recommended_action="review",
                location={"start_char": m.start(), "end_char": m.end()},
                detector="content_sanitizer.html_comment",
            ))
    for m in _HIDDEN_CSS.finditer(nfc):
        findings.add(SecurityFinding(
            risk=Severity.HIGH,
            category="hidden_html",
            source_id=source_id,
            evidence=m.group(0)[:200],
            recommended_action="review",
            location={"start_char": m.start(), "end_char": m.end()},
            detector="content_sanitizer.hidden_css",
        ))
    for pattern, label in ((_BASE64_BLOB, "base64"), (_HEX_BLOB, "hex")):
        for m in pattern.finditer(nfc):
            findings.add(SecurityFinding(
                risk=Severity.MEDIUM,
                category="encoded_content",
                source_id=source_id,
                evidence=f"suspicious {label} block, {m.end() - m.start()} chars",
                recommended_action="review",
                location={"start_char": m.start(), "end_char": m.end()},
                detector=f"content_sanitizer.{label}",
            ))

    return result
