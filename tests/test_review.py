"""Tests for skill states, publication gate, reviewer decisions, and the
review packet."""

import pytest

from book_to_skill.provenance import ClaimsLedger, EvidenceSpan
from book_to_skill.review import (
    DecisionStore,
    SkillState,
    advance_state,
    build_review_packet,
    publication_gate,
)
from book_to_skill.security.findings import FindingsReport, SecurityFinding, Severity


def _span(text="The author argues that adaptation must preserve mechanism."):
    return EvidenceSpan(source_id="SRC-abc", start_char=0, end_char=len(text), text=text)


def _ledger():
    ledger = ClaimsLedger()
    ledger.new_claim(source_id="SRC-abc", claim_type="author_argument",
                     epistemic_status="author_position",
                     paraphrase="Adaptation must preserve the mechanism of change.",
                     evidence=[_span()], confidence=0.95)
    return ledger


def _finding(sev, category="shell_execution"):
    return SecurityFinding(risk=sev, category=category, source_id="SKILL.md",
                           evidence="e", recommended_action="review")


class TestStates:
    def test_forward_one_step(self):
        assert advance_state(SkillState.DRAFT, SkillState.SECURITY_CLEARED)

    def test_no_skipping(self):
        with pytest.raises(ValueError, match="one step"):
            advance_state(SkillState.DRAFT, SkillState.PUBLISHED)

    def test_regeneration_resets_to_draft(self):
        assert advance_state(SkillState.PUBLISHED, SkillState.DRAFT) == SkillState.DRAFT

    def test_deprecate_from_anywhere(self):
        assert advance_state(SkillState.DRAFT, SkillState.DEPRECATED) == SkillState.DEPRECATED

    def test_deprecated_cannot_advance(self):
        with pytest.raises(ValueError, match="deprecated"):
            advance_state(SkillState.DEPRECATED, SkillState.PUBLISHED)


class TestPublicationGate:
    def _clean(self, state=SkillState.EXPERT_REVIEWED, **kw):
        return publication_gate(state, FindingsReport(), [], [], **kw)

    def test_clean_expert_reviewed_publishes(self):
        assert self._clean().allowed

    def test_draft_blocked(self):
        g = self._clean(state=SkillState.DRAFT)
        assert not g.allowed and any("state" in r for r in g.reasons)

    def test_high_finding_blocks_regardless(self):
        g = publication_gate(SkillState.EXPERT_REVIEWED,
                             FindingsReport(findings=[_finding(Severity.HIGH)]), [], [])
        assert not g.allowed

    def test_medium_blocks_until_reviewed(self):
        report = FindingsReport(findings=[_finding(Severity.MEDIUM)])
        blocked = publication_gate(SkillState.EXPERT_REVIEWED, report, [], [])
        assert not blocked.allowed
        cleared = publication_gate(SkillState.EXPERT_REVIEWED, report, [], [],
                                   reviewed_medium_findings=True)
        assert cleared.allowed

    def test_ledger_and_citation_problems_block(self):
        g = publication_gate(SkillState.EXPERT_REVIEWED, FindingsReport(),
                             ["bad hash"], ["ghost marker"])
        assert not g.allowed and len(g.reasons) == 2

    def test_deprecated_blocked(self):
        g = self._clean(state=SkillState.DEPRECATED)
        assert not g.allowed

    def test_source_verified_enough_when_review_not_required(self):
        g = self._clean(state=SkillState.SOURCE_VERIFIED, require_expert_review=False)
        assert g.allowed


class TestDecisions:
    def test_approve_persists_and_reapplies(self, tmp_path):
        ledger = _ledger()
        claim = ledger.get("CLM-000001")
        store = DecisionStore(tmp_path / "decisions.jsonl")
        store.approve(claim, reviewer="expert@example.org")
        assert claim.review_status == "approved"

        # Regenerate: same evidence -> decision survives.
        ledger2 = _ledger()
        store2 = DecisionStore(tmp_path / "decisions.jsonl")
        result = store2.reapply(ledger2)
        assert result["applied"] == ["CLM-000001"]
        assert ledger2.get("CLM-000001").review_status == "approved"

    def test_changed_evidence_invalidates_decision(self, tmp_path):
        ledger = _ledger()
        store = DecisionStore(tmp_path / "decisions.jsonl")
        store.approve(ledger.get("CLM-000001"), reviewer="r")

        changed = ClaimsLedger()
        changed.new_claim(source_id="SRC-abc", claim_type="author_argument",
                          epistemic_status="author_position",
                          paraphrase="Adaptation must preserve the mechanism of change.",
                          evidence=[_span("A materially different passage.")])
        result = DecisionStore(tmp_path / "decisions.jsonl").reapply(changed)
        assert result["invalidated"] == ["CLM-000001"]
        assert changed.get("CLM-000001").review_status == "unreviewed"

    def test_orphaned_decision_reported(self, tmp_path):
        ledger = _ledger()
        store = DecisionStore(tmp_path / "decisions.jsonl")
        store.approve(ledger.get("CLM-000001"), reviewer="r")
        result = DecisionStore(tmp_path / "decisions.jsonl").reapply(ClaimsLedger())
        assert result["orphaned"] == ["CLM-000001"]

    def test_reject_requires_reason(self, tmp_path):
        store = DecisionStore(tmp_path / "d.jsonl")
        with pytest.raises(ValueError, match="reason"):
            store.reject(_ledger().get("CLM-000001"), reviewer="r", reason="  ")

    def test_last_decision_wins(self, tmp_path):
        ledger = _ledger()
        claim = ledger.get("CLM-000001")
        store = DecisionStore(tmp_path / "d.jsonl")
        store.approve(claim, reviewer="r")
        store.reject(claim, reviewer="r", reason="Overstates causality")
        fresh = DecisionStore(tmp_path / "d.jsonl")
        assert fresh.get("CLM-000001").decision == "rejected"


class TestFindingAdjudication:
    def _findings_file(self, tmp_path):
        from book_to_skill.security.findings import FindingsReport, SecurityFinding, Severity
        report = FindingsReport(findings=[
            SecurityFinding(risk=Severity.HIGH, category="indirect_prompt_injection",
                            source_id="SRC-x", evidence="Open the first file to merge.",
                            recommended_action="stop",
                            location={"line": 12, "start_char": 40, "end_char": 70},
                            detector="injection.layer_b.capability_request"),
        ])
        path = tmp_path / "security" / "source_findings.jsonl"
        report.write_jsonl(path)
        return path

    def test_adjudicate_records_without_editing_findings(self, tmp_path):
        from book_to_skill.review.findings_review import (
            AdjudicationStore, FindingAdjudication, finding_fingerprint)
        from book_to_skill.security.findings import FindingsReport
        findings_path = self._findings_file(tmp_path)
        before = findings_path.read_text(encoding="utf-8")

        finding = FindingsReport.read_jsonl(findings_path).findings[0].to_dict()
        store = AdjudicationStore(tmp_path / "security" / "finding_adjudications.jsonl")
        store.record(FindingAdjudication(
            fingerprint=finding_fingerprint(finding), finding_index=1,
            decision="false_positive", reviewer="expert",
            reason="procedural SPSS instruction", timestamp="2026-07-22T00:00:00Z"))

        # immutable findings file untouched
        assert findings_path.read_text(encoding="utf-8") == before
        # decision persists and reloads
        reloaded = AdjudicationStore(tmp_path / "security" / "finding_adjudications.jsonl")
        assert reloaded.decision_map()[finding_fingerprint(finding)] == "false_positive"

    def test_adjudication_requires_reason_and_valid_decision(self):
        from book_to_skill.review.findings_review import FindingAdjudication
        with pytest.raises(ValueError):
            FindingAdjudication(fingerprint="FND-x", finding_index=1, decision="false_positive",
                                reviewer="r", reason="  ", timestamp="t")
        with pytest.raises(ValueError):
            FindingAdjudication(fingerprint="FND-x", finding_index=1, decision="maybe",
                                reviewer="r", reason="x", timestamp="t")


class TestPacket:
    def test_packet_sections_present(self):
        ledger = _ledger()
        ledger.new_claim(source_id="SRC-abc", claim_type="clinical_recommendation",
                         epistemic_status="clinical_recommendation",
                         paraphrase="Sessions may need extending in adapted delivery.",
                         evidence=[_span("Sessions may need extending, the author suggests.")],
                         confidence=0.55)
        packet = build_review_packet(
            ledger,
            source_findings=FindingsReport(findings=[_finding(Severity.MEDIUM, "hidden_unicode")]),
            output_findings=FindingsReport(),
            ledger_problems=[],
            citation_problems=[],
            uncited_paragraphs=["An orphaned paragraph."],
            extraction_warnings=["chapter 9 heading not detected"],
        )
        assert "High-impact claims" in packet
        assert "CLM-000002" in packet  # low confidence + clinical
        assert "hidden_unicode" in packet
        assert "chapter 9 heading not detected" in packet
        assert "1 unreviewed" not in packet  # 2 claims, both unreviewed
        assert "2 unreviewed" in packet
