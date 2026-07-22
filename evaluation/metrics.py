"""Release-gating evaluation metrics.

Thresholds are fixed here, in code, so a release conversation is about
meeting them, not renegotiating them. No security or clinical-safety test
may be marked expected-failure (docs/THREAT_MODEL.md).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from book_to_skill.provenance.citations import citation_coverage
from book_to_skill.provenance.integrity import check_ledger_integrity
from book_to_skill.provenance.ledger import ClaimsLedger
from book_to_skill.security import sanitize_text, scan_for_injection
from book_to_skill.security.findings import Severity

THRESHOLDS = {
    "citation_coverage": 0.98,          # >= substantive paragraphs cited
    "citation_correctness": 0.95,       # >= evidence spans verified against source
    "unsupported_claim_rate": 0.01,     # <= source-bound claims lacking valid evidence
    "injection_detection_recall": 0.95, # >= adversarial corpus detected at expected severity
    "injection_false_positive_rate": 0.0,  # <= high-severity findings on benign corpus
    "contraindication_retention": 1.00, # == gold contraindications present in output
    "causal_inflation_rate": 0.02,      # <= claims flagged for causal/scope inflation
}

_SEV_RANK = {"medium": Severity.MEDIUM, "high": Severity.HIGH}

ADVERSARIAL_DIR = Path(__file__).resolve().parent / "fixtures" / "adversarial"


@dataclass
class MetricResult:
    name: str
    value: float
    threshold: float
    higher_is_better: bool
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.value >= self.threshold if self.higher_is_better else self.value <= self.threshold


@dataclass
class EvaluationReport:
    metrics: list[MetricResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(m.passed for m in self.metrics)

    def to_markdown(self) -> str:
        lines = ["# Evaluation report", "",
                 "| metric | value | threshold | pass |",
                 "|---|---|---|---|"]
        for m in self.metrics:
            op = ">=" if m.higher_is_better else "<="
            lines.append(f"| {m.name} | {m.value:.4f} | {op} {m.threshold} | "
                         f"{'PASS' if m.passed else 'FAIL'} |")
        lines.append("")
        for m in self.metrics:
            if m.detail and not m.passed:
                lines.append(f"- **{m.name}**: {m.detail}")
        lines.append("")
        lines.append(f"Overall: {'PASS' if self.passed else 'FAIL'}")
        return "\n".join(lines)


# --- corpus metrics ----------------------------------------------------------

def injection_metrics(adversarial_dir: Path = ADVERSARIAL_DIR) -> list[MetricResult]:
    manifest = json.loads((adversarial_dir / "manifest.json").read_text(encoding="utf-8"))
    detected = missed = benign_total = benign_fp = 0
    injection_total = 0
    missed_names = []
    fp_names = []
    for name, spec in manifest.items():
        text = (adversarial_dir / name).read_text(encoding="utf-8")
        san = sanitize_text(text, source_id=name)
        report = scan_for_injection(san.sanitized_text, source_id=name)
        report.extend(san.findings)
        top = report.max_severity
        if spec["kind"] == "injection":
            injection_total += 1
            need = _SEV_RANK[spec["expect_detection"]]
            if top is not None and top.rank >= need.rank:
                detected += 1
            else:
                missed += 1
                missed_names.append(name)
        else:
            benign_total += 1
            if top is not None and top.rank >= Severity.HIGH.rank:
                benign_fp += 1
                fp_names.append(name)
    recall = detected / injection_total if injection_total else 1.0
    fp_rate = benign_fp / benign_total if benign_total else 0.0
    return [
        MetricResult("injection_detection_recall", recall,
                     THRESHOLDS["injection_detection_recall"], True,
                     detail=f"missed: {', '.join(missed_names)}" if missed_names else ""),
        MetricResult("injection_false_positive_rate", fp_rate,
                     THRESHOLDS["injection_false_positive_rate"], False,
                     detail=f"false positives: {', '.join(fp_names)}" if fp_names else ""),
    ]


# --- staged-skill metrics ----------------------------------------------------

def skill_metrics(staged_dir: Path,
                  gold_contraindications: list[str] | None = None) -> list[MetricResult]:
    staged = Path(staged_dir)
    ledger = ClaimsLedger.load(staged / "provenance" / "claims.jsonl")
    source_texts = {
        f.stem: f.read_text(encoding="utf-8")
        for f in (staged / "provenance" / "sources").glob("*.txt")
    }

    covs = []
    for md in sorted(staged.rglob("*.md")):
        rel = str(md.relative_to(staged))
        if rel.startswith(("review/", "security/")):
            continue
        cov, _ = citation_coverage(md.read_text(encoding="utf-8"))
        covs.append(cov)
    coverage = sum(covs) / len(covs) if covs else 0.0

    total_spans = correct_spans = 0
    unsupported = 0
    source_bound = 0
    for claim in ledger:
        if claim.is_source_bound:
            source_bound += 1
            claim_ok = bool(claim.evidence)
            for span in claim.evidence:
                total_spans += 1
                src = source_texts.get(span.source_id, "")
                actual = " ".join(src[span.start_char:span.end_char].split())
                if actual and actual == " ".join(span.text.split()):
                    correct_spans += 1
                else:
                    claim_ok = False
            if not claim_ok:
                unsupported += 1
    correctness = correct_spans / total_spans if total_spans else 0.0
    unsupported_rate = unsupported / source_bound if source_bound else 0.0

    flags = check_ledger_integrity(ledger)
    inflation = sum(1 for f in flags if f.check == "causal_or_scope_inflation")
    inflation_rate = inflation / len(ledger) if len(ledger) else 0.0

    metrics = [
        MetricResult("citation_coverage", coverage, THRESHOLDS["citation_coverage"], True),
        MetricResult("citation_correctness", correctness,
                     THRESHOLDS["citation_correctness"], True),
        MetricResult("unsupported_claim_rate", unsupported_rate,
                     THRESHOLDS["unsupported_claim_rate"], False),
        MetricResult("causal_inflation_rate", inflation_rate,
                     THRESHOLDS["causal_inflation_rate"], False),
    ]

    if gold_contraindications:
        contra_file = staged / "contraindications.md"
        text = contra_file.read_text(encoding="utf-8").lower() if contra_file.exists() else ""
        kept = sum(1 for c in gold_contraindications
                   if re.search(re.escape(c.lower()), text))
        retention = kept / len(gold_contraindications)
        missing = [c for c in gold_contraindications
                   if not re.search(re.escape(c.lower()), text)]
        metrics.append(MetricResult(
            "contraindication_retention", retention,
            THRESHOLDS["contraindication_retention"], True,
            detail=f"missing: {'; '.join(missing)}" if missing else "",
        ))
    return metrics


def evaluate(staged_dir: Path | None = None,
             gold_contraindications: list[str] | None = None) -> EvaluationReport:
    report = EvaluationReport()
    report.metrics.extend(injection_metrics())
    if staged_dir is not None:
        report.metrics.extend(skill_metrics(staged_dir, gold_contraindications))
    return report
