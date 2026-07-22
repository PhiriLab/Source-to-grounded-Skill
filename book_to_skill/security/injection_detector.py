"""Layered indirect-prompt-injection detection for extracted source text.

Layer A: deterministic phrase patterns (high confidence, high/critical).
Layer B: structural anomalies — imperatives addressed to an AI/agent,
         commands requesting capabilities a book never needs, instructions
         to suppress disclosure or citations.
Layer C: optional model-assisted classifier. Interface only: a registered
         classifier may ADD findings or RAISE severity; it can never remove
         or downgrade deterministic findings (docs/THREAT_MODEL.md).

Detection is a filter, not the trust boundary — capability minimisation and
human review remain in place regardless of what this module finds.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from book_to_skill.security.findings import FindingsReport, SecurityFinding, Severity

# --- Layer A: deterministic phrases -----------------------------------------
# (pattern, severity). Case-insensitive, matched per line so locations are
# reportable and a phrase inside one long paragraph is still found.
_LAYER_A: list[tuple[re.Pattern, Severity]] = [
    (re.compile(p, re.IGNORECASE), sev)
    for p, sev in [
        (r"\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|earlier|above)\s+instructions\b", Severity.CRITICAL),
        (r"\bdisregard\s+(?:all\s+|any\s+)?(?:previous|prior|earlier|your)\s+(?:instructions|guidelines|rules)\b", Severity.CRITICAL),
        (r"\bsystem\s+prompt\b", Severity.HIGH),
        (r"\bdeveloper\s+message\b", Severity.HIGH),
        (r"\byou\s+are\s+(?:chatgpt|claude|copilot|an?\s+ai\s+(?:assistant|agent|model))\b", Severity.HIGH),
        (r"\bexecute\s+(?:this|the\s+following)\s+(?:command|script|code)\b", Severity.CRITICAL),
        (r"\bwrite\s+to\s+~/\.(?:claude|copilot|agents|config|ssh)\b", Severity.CRITICAL),
        (r"\breveal\s+(?:your\s+)?(?:secrets?|system\s+prompt|instructions)\b", Severity.HIGH),
        (r"\b(?:send|upload|exfiltrate|post)\s+(?:this|the|that)\s+(?:file|data|content|conversation)\b", Severity.CRITICAL),
        (r"\bdo\s+not\s+(?:tell|inform|alert|notify)\s+the\s+user\b", Severity.CRITICAL),
        (r"\boverride\s+(?:the\s+)?polic(?:y|ies)\b", Severity.HIGH),
        (r"\bnew\s+instructions?\s*:\s*", Severity.MEDIUM),
        (r"\bwhen\s+(?:you|the\s+(?:agent|assistant|ai))\s+(?:read|see|process)e?s?\s+this\b", Severity.HIGH),
        (r"\bcurl\s+-[A-Za-z]*s[A-Za-z]*\s+\S+\s*\|\s*(?:ba)?sh\b", Severity.CRITICAL),
        (r"\brm\s+-rf\s+[~/]", Severity.CRITICAL),
    ]
]

# --- Layer B: structural anomalies -------------------------------------------
_AGENT_ADDRESS = re.compile(
    r"^\s*(?:dear|attention|note\s+to|hey|hello)?,?\s*(?:ai|assistant|agent|model|claude|copilot|llm)\b[^.\n]{0,80}[:,]",
    re.IGNORECASE,
)
_IMPERATIVE_CAPABILITY = re.compile(
    r"\b(?:run|execute|open|read|write|modify|delete|access|fetch|download|install)\b"
    r"[^.\n]{0,60}?"
    r"\b(?:file|folder|directory|shell|terminal|command|credential|password|token|api\s+key|environment\s+variable|network|url|endpoint)s?\b",
    re.IGNORECASE,
)
_FORMAT_REDEFINITION = re.compile(
    r"\b(?:respond|reply|answer|output)\s+(?:only\s+)?(?:in|with|using)\s+(?:json|yaml|base64|code|the\s+following\s+format)\b",
    re.IGNORECASE,
)
_CITATION_SUPPRESSION = re.compile(
    r"\b(?:omit|skip|remove|without|no\s+need\s+for)\s+(?:the\s+)?(?:citations?|sources?|attributions?|provenance|references?)\b",
    re.IGNORECASE,
)

# Lines matching Layer B only count when they look imperative/instructional
# rather than descriptive prose ("The researcher must download the dataset"
# is normal book content). Heuristic: sentence starts with the verb, or is
# addressed to an agent, or appears in a footnote/metadata-like short line.
_STARTS_IMPERATIVE = re.compile(
    r"^\s*(?:please\s+)?(?:now\s+)?(?:run|execute|open|write|modify|delete|access|fetch|download|install|respond|reply|output|ignore|disregard)\b",
    re.IGNORECASE,
)
# Footnote/list markers that may precede a hidden instruction: superscript
# digits, "[1]", "1.", "*", "†". Stripped before the imperative check so an
# instruction buried in a footnote still registers as line-initial.
_FOOTNOTE_MARKER = re.compile(r"^\s*(?:[¹²³⁰-⁹]+|\[\d{1,3}\]|\d{1,3}[.)]|[*†‡])\s*")


def _instruction_body(line: str) -> str:
    return _FOOTNOTE_MARKER.sub("", line, count=1)

ClassifierFn = Callable[[str, str], list[SecurityFinding]]
_classifier: Optional[ClassifierFn] = None


def register_classifier(fn: ClassifierFn) -> None:
    """Register a Layer C classifier: fn(text, source_id) -> findings.

    Classifier findings are appended to deterministic results; they can add
    or raise, never remove.
    """
    global _classifier
    _classifier = fn


def scan_for_injection(text: str, source_id: str = "source") -> FindingsReport:
    report = FindingsReport()
    offset = 0
    for line_no, line in enumerate(text.splitlines(keepends=True), start=1):
        stripped = _instruction_body(line.strip())
        loc = {"line": line_no, "start_char": offset, "end_char": offset + len(line)}

        for pattern, severity in _LAYER_A:
            m = pattern.search(stripped)
            if m:
                report.add(SecurityFinding(
                    risk=severity,
                    category="indirect_prompt_injection",
                    source_id=source_id,
                    evidence=stripped[:200],
                    recommended_action="quarantine" if severity == Severity.CRITICAL else "stop",
                    location=loc,
                    detector="injection.layer_a",
                    note=f"pattern: {pattern.pattern[:80]}",
                ))
                break  # one Layer A finding per line is enough

        if _AGENT_ADDRESS.search(stripped):
            report.add(SecurityFinding(
                risk=Severity.HIGH,
                category="indirect_prompt_injection",
                source_id=source_id,
                evidence=stripped[:200],
                recommended_action="stop",
                location=loc,
                detector="injection.layer_b.agent_address",
            ))
        elif _STARTS_IMPERATIVE.search(stripped):
            if _IMPERATIVE_CAPABILITY.search(stripped):
                report.add(SecurityFinding(
                    risk=Severity.HIGH,
                    category="indirect_prompt_injection",
                    source_id=source_id,
                    evidence=stripped[:200],
                    recommended_action="stop",
                    location=loc,
                    detector="injection.layer_b.capability_request",
                ))
            elif _FORMAT_REDEFINITION.search(stripped):
                report.add(SecurityFinding(
                    risk=Severity.MEDIUM,
                    category="indirect_prompt_injection",
                    source_id=source_id,
                    evidence=stripped[:200],
                    recommended_action="analysis_only",
                    location=loc,
                    detector="injection.layer_b.format_redefinition",
                ))
        if _CITATION_SUPPRESSION.search(stripped) and _STARTS_IMPERATIVE.search(stripped):
            report.add(SecurityFinding(
                risk=Severity.MEDIUM,
                category="citation_suppression",
                source_id=source_id,
                evidence=stripped[:200],
                recommended_action="analysis_only",
                location=loc,
                detector="injection.layer_b.citation_suppression",
            ))
        offset += len(line)

    if _classifier is not None:
        report.findings.extend(_classifier(text, source_id))
    return report
