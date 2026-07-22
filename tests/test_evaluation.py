"""Evaluation harness tests. Adversarial detection thresholds are hard
gates: none of these may be xfail."""

import json
from pathlib import Path

from evaluation.metrics import (
    ADVERSARIAL_DIR,
    THRESHOLDS,
    evaluate,
    injection_metrics,
    skill_metrics,
)
from book_to_skill.provenance import ClaimsLedger, EvidenceSpan


class TestAdversarialCorpus:
    def test_manifest_covers_all_fixtures(self):
        manifest = json.loads((ADVERSARIAL_DIR / "manifest.json").read_text())
        files = {p.name for p in ADVERSARIAL_DIR.glob("*.txt")}
        assert files == set(manifest)

    def test_injection_recall_meets_threshold(self):
        results = {m.name: m for m in injection_metrics()}
        recall = results["injection_detection_recall"]
        assert recall.passed, f"recall {recall.value:.2f}: {recall.detail}"
        assert recall.value >= THRESHOLDS["injection_detection_recall"]

    def test_no_high_severity_false_positives_on_benign(self):
        results = {m.name: m for m in injection_metrics()}
        fp = results["injection_false_positive_rate"]
        assert fp.passed, fp.detail


class TestSkillMetrics:
    def _staged(self, tmp_path, paraphrase, cited=True):
        staged = tmp_path / "skill"
        (staged / "provenance" / "sources").mkdir(parents=True)
        passage = ("The findings suggest that engagement may be associated "
                   "with better retention in this sample.")
        (staged / "provenance" / "sources" / "SRC-x.txt").write_text(passage, encoding="utf-8")
        ledger = ClaimsLedger()
        ledger.new_claim(
            source_id="SRC-x", claim_type="empirical_finding",
            epistemic_status="empirical_finding", paraphrase=paraphrase,
            evidence=[EvidenceSpan(source_id="SRC-x", start_char=0,
                                   end_char=len(passage), text=passage)],
        )
        ledger.save(staged / "provenance" / "claims.jsonl")
        marker = " [SRC:BOOK1:CH01]" if cited else ""
        (staged / "SKILL.md").write_text(
            f"# Skill\n\nA substantive paragraph restating the finding with "
            f"enough length to require a citation marker in coverage terms."
            f"{marker}\n", encoding="utf-8")
        return staged

    def test_clean_skill_passes(self, tmp_path):
        staged = self._staged(
            tmp_path,
            "Engagement may be associated with better retention in this sample.")
        results = {m.name: m for m in skill_metrics(staged)}
        assert results["citation_coverage"].passed
        assert results["citation_correctness"].value == 1.0
        assert results["unsupported_claim_rate"].value == 0.0
        assert results["causal_inflation_rate"].passed

    def test_uncited_paragraph_fails_coverage(self, tmp_path):
        staged = self._staged(
            tmp_path,
            "Engagement may be associated with better retention in this sample.",
            cited=False)
        results = {m.name: m for m in skill_metrics(staged)}
        assert not results["citation_coverage"].passed

    def test_causal_inflation_fails_gate(self, tmp_path):
        staged = self._staged(tmp_path, "Engagement causes better retention in people.")
        results = {m.name: m for m in skill_metrics(staged)}
        assert not results["causal_inflation_rate"].passed

    def test_contraindication_retention_exact(self, tmp_path):
        staged = self._staged(
            tmp_path,
            "Engagement may be associated with better retention in this sample.")
        (staged / "contraindications.md").write_text(
            "# Contraindications\n\n- Active psychosis\n- Acute suicidality\n",
            encoding="utf-8")
        gold = ["active psychosis", "acute suicidality"]
        results = {m.name: m for m in skill_metrics(staged, gold)}
        assert results["contraindication_retention"].value == 1.0

        gold_missing = gold + ["untreated substance dependence"]
        results = {m.name: m for m in skill_metrics(staged, gold_missing)}
        r = results["contraindication_retention"]
        assert not r.passed
        assert "untreated substance dependence" in r.detail

    def test_report_markdown(self, tmp_path):
        staged = self._staged(
            tmp_path,
            "Engagement may be associated with better retention in this sample.")
        report = evaluate(staged)
        md = report.to_markdown()
        assert "| citation_coverage |" in md
        assert "injection_detection_recall" in md
        assert md.strip().endswith(("PASS", "FAIL"))
