"""Security boundary between untrusted document content and skill generation.

Pipeline placement (see docs/THREAT_MODEL.md):

    extraction -> content_sanitizer -> injection_detector -> policy gate
    ... host-agent generation into staging ...
    output_scanner -> policy gate -> review -> publish

All detection here is deterministic. A model may later *raise* the severity
of a finding, never lower or clear one.
"""

from book_to_skill.security.findings import (
    Severity,
    SecurityFinding,
    FindingsReport,
)
from book_to_skill.security.content_sanitizer import sanitize_text
from book_to_skill.security.injection_detector import scan_for_injection
from book_to_skill.security.output_scanner import scan_generated_file, scan_generated_dir
from book_to_skill.security.policy import SecurityPolicy, GateDecision, evaluate_findings

__all__ = [
    "Severity",
    "SecurityFinding",
    "FindingsReport",
    "sanitize_text",
    "scan_for_injection",
    "scan_generated_file",
    "scan_generated_dir",
    "SecurityPolicy",
    "GateDecision",
    "evaluate_findings",
]
