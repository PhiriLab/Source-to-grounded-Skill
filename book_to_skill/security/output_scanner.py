"""Scanner for generated skill files, run before review/publication.

A generated book skill is a read-only reference artifact: it should contain
no shell commands, network access, credential references, agent identity
redefinition, or disclosure suppression. Anything of that shape blocks
publication until a human reviews it (docs/THREAT_MODEL.md, T2).

The converter's own SKILL.md legitimately contains shell blocks; this
scanner is for *generated* skills only.
"""

from __future__ import annotations

import re
from pathlib import Path

from book_to_skill.security.content_sanitizer import _BIDI_CONTROLS, _INVISIBLE
from book_to_skill.security.findings import FindingsReport, SecurityFinding, Severity

_RULES: list[tuple[re.Pattern, str, Severity, str]] = [
    (re.compile(r"(?:^|\s)(?:curl|wget)\s+\S+", re.MULTILINE), "network_access", Severity.HIGH,
     "network fetch command"),
    (re.compile(r"(?:^|\s)(?:ssh|scp|sftp|rsync)\s+\S+", re.MULTILINE), "network_access", Severity.HIGH,
     "remote-access command"),
    (re.compile(r"(?:^|\s)sudo\s+\S+", re.MULTILINE), "shell_execution", Severity.HIGH,
     "privilege escalation"),
    (re.compile(r"\brm\s+-[a-z]*rf?\b|\brm\s+-[a-z]*fr?\b"), "destructive_file_operation", Severity.CRITICAL,
     "recursive/forced delete"),
    (re.compile(r"\b(?:eval|exec)\s*\(|\|\s*(?:ba|z|da)?sh\b|base64\s+(?:-d|--decode)"), "shell_execution",
     Severity.CRITICAL, "dynamic/encoded execution"),
    (re.compile(r"```(?:sh|bash|shell|zsh)\b"), "shell_execution", Severity.MEDIUM,
     "shell code block in a reference skill"),
    (re.compile(r"\$\{?[A-Z_]*(?:TOKEN|SECRET|PASSWORD|API_?KEY|CREDENTIAL)[A-Z_]*\}?", re.IGNORECASE),
     "credential_access", Severity.HIGH, "credential/environment-variable reference"),
    (re.compile(r"~/\.(?:ssh|aws|config/gh|netrc)\b|/etc/(?:passwd|shadow)\b"), "credential_access",
     Severity.CRITICAL, "sensitive path reference"),
    (re.compile(r"\byou\s+are\s+(?:now\s+)?(?:a\s+)?(?:chatgpt|claude|copilot|dan\b|an?\s+unrestricted)", re.IGNORECASE),
     "agent_role_redefinition", Severity.CRITICAL, "agent identity redefinition"),
    (re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|other)\s+(?:instructions|skills|rules)\b", re.IGNORECASE),
     "agent_role_redefinition", Severity.CRITICAL, "instruction override"),
    (re.compile(r"\bdo\s+not\s+(?:tell|inform|mention|disclose)\s+(?:this\s+)?(?:to\s+)?the\s+user\b", re.IGNORECASE),
     "disclosure_suppression", Severity.CRITICAL, "disclosure suppression"),
    (re.compile(r"\bwithout\s+(?:citing|attribution|mentioning\s+the\s+source)\b", re.IGNORECASE),
     "citation_suppression", Severity.HIGH, "citation suppression"),
    (re.compile(r"https?://(?!(?:doi\.org|dx\.doi\.org|www\.who\.int|pubmed\.ncbi\.nlm\.nih\.gov|clinicaltrials\.gov|isrctn\.com|osf\.io)\b)\S+"),
     "unverified_external_url", Severity.LOW, "external URL (verify before trusting)"),
]

# Identifier patterns for restricted material (participant IDs, NHS numbers,
# emails, phone numbers). Deliberately conservative; applied only when the
# privacy classification asks for it.
_IDENTIFIER_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "email address"),
    (re.compile(r"\b\d{3}[ -]?\d{3}[ -]?\d{4}\b"), "NHS-number/phone-shaped digits"),
    (re.compile(r"\b(?:participant|subject|patient)\s*(?:id|#|number)?\s*[:=]?\s*[A-Z0-9-]{3,}\b", re.IGNORECASE),
     "participant identifier"),
    (re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b.{0,20}\b(?:dob|birth)\b|\b(?:dob|date\s+of\s+birth)\b.{0,20}\b\d{1,2}[/.-]\d{1,2}[/.-](?:19|20)?\d{2}\b", re.IGNORECASE),
     "date of birth"),
]


def _hidden_unicode_findings(text: str, file_id: str) -> list[SecurityFinding]:
    hits = [ch for ch in text if ch in _BIDI_CONTROLS or ch in _INVISIBLE]
    if not hits:
        return []
    return [SecurityFinding(
        risk=Severity.HIGH,
        category="hidden_unicode",
        source_id=file_id,
        evidence=f"{len(hits)} hidden/bidi character(s) in generated output",
        recommended_action="stop",
        detector="output_scanner.hidden_unicode",
    )]


def scan_generated_text(text: str, file_id: str, check_identifiers: bool = False) -> FindingsReport:
    report = FindingsReport()
    for pattern, category, severity, label in _RULES:
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            report.add(SecurityFinding(
                risk=severity,
                category=category,
                source_id=file_id,
                evidence=m.group(0)[:200],
                recommended_action="stop" if severity.rank >= Severity.HIGH.rank else "review",
                location={"line": line_no, "start_char": m.start(), "end_char": m.end()},
                detector="output_scanner",
                note=label,
            ))
    for f in _hidden_unicode_findings(text, file_id):
        report.add(f)
    if check_identifiers:
        for pattern, label in _IDENTIFIER_RULES:
            for m in pattern.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                report.add(SecurityFinding(
                    risk=Severity.CRITICAL,
                    category="identifier_exposure",
                    source_id=file_id,
                    evidence=label,  # deliberately NOT the matched text
                    recommended_action="stop",
                    location={"line": line_no, "start_char": m.start(), "end_char": m.end()},
                    detector="output_scanner.identifiers",
                ))
    return report


def scan_generated_file(path: Path, check_identifiers: bool = False) -> FindingsReport:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return scan_generated_text(text, file_id=str(path), check_identifiers=check_identifiers)


def scan_generated_dir(directory: Path, check_identifiers: bool = False) -> FindingsReport:
    """Scan every markdown/text/yaml/json file under a staged skill directory."""
    report = FindingsReport()
    directory = Path(directory)
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            report.add(SecurityFinding(
                risk=Severity.CRITICAL,
                category="path_traversal",
                source_id=str(path),
                evidence="symlink inside staged skill output",
                recommended_action="stop",
                detector="output_scanner.symlink",
            ))
            continue
        if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt", ".yaml", ".yml", ".json", ".jsonl", ".csv"}:
            report.extend(scan_generated_file(path, check_identifiers=check_identifiers))
    return report
