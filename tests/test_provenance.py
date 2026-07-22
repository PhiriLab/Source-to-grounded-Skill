"""Tests for provenance entities, claims ledger, citations, integrity
checks, and claim tracing."""

import json

import pytest

from book_to_skill.provenance import (
    Claim,
    ClaimsLedger,
    EvidenceSpan,
    GenerationManifest,
    Source,
    citation_coverage,
    parse_markers,
    span_hash,
    trace_claim,
)
from book_to_skill.provenance.citations import validate_markers
from book_to_skill.provenance.integrity import check_ledger_integrity, check_modality
from book_to_skill.provenance.ledger import MAX_EVIDENCE_CHARS, LedgerError


def _span(text="Culturally adapted CBT was associated with symptom reduction in this sample.",
          source_id="SRC-abc123", start=100):
    return EvidenceSpan(source_id=source_id, start_char=start,
                        end_char=start + len(text), text=text)


def _claim(ledger, paraphrase="Adapted CBT was associated with symptom reduction in the study sample.",
           status="empirical_finding", ctype="empirical_finding", **kw):
    return ledger.new_claim(
        source_id=kw.pop("source_id", "SRC-abc123"),
        claim_type=ctype,
        epistemic_status=status,
        paraphrase=paraphrase,
        evidence=kw.pop("evidence", [_span()]),
        **kw,
    )


class TestModels:
    def test_source_bound_claim_requires_evidence(self):
        with pytest.raises(ValueError, match="requires at least one evidence span"):
            Claim(claim_id="CLM-000001", source_id="SRC-x", claim_type="definition",
                  epistemic_status="close_paraphrase", paraphrase="a definition",
                  evidence=[])

    def test_external_context_allowed_without_evidence(self):
        c = Claim(claim_id="CLM-000002", source_id="", claim_type="editorial_synthesis",
                  epistemic_status="external_contextualisation",
                  paraphrase="WHO later updated this guidance.")
        assert not c.is_source_bound

    def test_unknown_status_rejected(self):
        with pytest.raises(ValueError, match="epistemic status"):
            Claim(claim_id="CLM-000003", source_id="SRC-x", claim_type="definition",
                  epistemic_status="vibes", paraphrase="x", evidence=[_span()])

    def test_privacy_class_validated(self):
        with pytest.raises(ValueError, match="privacy"):
            Source(source_id="SRC-x", title="T", path="/p", sha256="0" * 64,
                   privacy="secret")

    def test_manifest_defaults_are_conservative(self):
        m = GenerationManifest(skill_id="test")
        assert m.state == "draft"
        assert m.world_knowledge == "off"


class TestLedger:
    def test_sequential_ids_and_roundtrip(self, tmp_path):
        ledger = ClaimsLedger()
        c1 = _claim(ledger)
        c2 = _claim(ledger, paraphrase="A second, distinct claim about mechanisms.")
        assert (c1.claim_id, c2.claim_id) == ("CLM-000001", "CLM-000002")
        path = tmp_path / "claims.jsonl"
        ledger.save(path)
        back = ClaimsLedger.load(path)
        assert len(back) == 2
        assert back.get("CLM-000002").paraphrase == c2.paraphrase
        assert back.get("CLM-000001").evidence[0].content_hash == span_hash(_span().text)

    def test_duplicate_id_rejected(self):
        ledger = ClaimsLedger()
        _claim(ledger)
        with pytest.raises(LedgerError, match="duplicate"):
            _claim(ledger, claim_id="CLM-000001")

    def test_oversize_evidence_flagged(self):
        ledger = ClaimsLedger()
        big = _span(text="x" * (MAX_EVIDENCE_CHARS + 1))
        _claim(ledger, evidence=[big])
        problems = ledger.validate()
        assert any("synthesise" in p for p in problems)

    def test_offset_verification_against_source(self):
        text = "PROLOGUE. " * 20 + "The mechanism must be preserved across adaptation." + " EPILOGUE." * 20
        start = text.index("The mechanism")
        passage = "The mechanism must be preserved across adaptation."
        ledger = ClaimsLedger()
        _claim(ledger, evidence=[EvidenceSpan(
            source_id="SRC-abc123", start_char=start,
            end_char=start + len(passage), text=passage)])
        assert ledger.validate({"SRC-abc123": text}) == []
        # Now shift offsets: citation present but WRONG — must be caught.
        ledger2 = ClaimsLedger()
        _claim(ledger2, evidence=[EvidenceSpan(
            source_id="SRC-abc123", start_char=0,
            end_char=len(passage), text=passage)])
        assert any("do not match" in p for p in ledger2.validate({"SRC-abc123": text}))

    def test_invalidated_by_source_change(self):
        passage = "Original wording of the supporting passage."
        ledger = ClaimsLedger()
        c = _claim(ledger, evidence=[EvidenceSpan(
            source_id="SRC-abc123", start_char=0,
            end_char=len(passage), text=passage)])
        assert ledger.invalidated_by({"SRC-abc123": passage}) == []
        stale = ledger.invalidated_by({"SRC-abc123": "Revised wording of the supporting passage!!"})
        assert stale == [c]

    def test_external_claim_with_source_attribution_invalid(self):
        ledger = ClaimsLedger()
        ledger.new_claim(source_id="SRC-abc123", claim_type="editorial_synthesis",
                         epistemic_status="external_contextualisation",
                         paraphrase="Later guidance changed.")
        assert any("must not be attributed" in p for p in ledger.validate())


class TestCitations:
    def test_marker_parsing(self):
        text = ("Mechanism must be preserved. [SRC:BOOK1:CH04:P87-91] "
                "See also [SRC:BOOK1:CH07] and [CLM:CLM-000481].")
        markers = parse_markers(text)
        assert markers[0].source == "BOOK1"
        assert markers[0].page_range == (87, 91)
        assert markers[1].section == "CH07"
        assert markers[2].claim == "CLM-000481"

    def test_char_locator(self):
        (m,) = parse_markers("x [SRC:BOOK1:CH04:C9283-9512]")
        assert m.char_range == (9283, 9512)

    def test_coverage_full(self):
        md = ("# Title\n\n"
              "A substantive paragraph long enough to demand a citation marker, "
              "carrying an argument from the book. [SRC:BOOK1:CH01:P10]\n\n"
              "| a | b |\n|---|---|\n")
        cov, uncited = citation_coverage(md)
        assert cov == 1.0 and uncited == []

    def test_coverage_detects_uncited(self):
        md = ("An uncited substantive paragraph making a factual assertion that "
              "definitely should have carried a provenance marker but does not.\n\n"
              "A cited one of comparable length carrying its provenance marker "
              "as required by the specification. [SRC:BOOK1:CH02:P20]\n")
        cov, uncited = citation_coverage(md)
        assert cov == 0.5 and len(uncited) == 1

    def test_validate_markers_resolution(self):
        md = "Claim. [SRC:BOOK1:CH04:P87] and [SRC:GHOST:CH01]"
        problems = validate_markers(md, known_sources={"BOOK1"},
                                    known_sections={"BOOK1:CH04"})
        assert problems == ["unresolvable source marker [SRC:GHOST:CH01]"]


class TestIntegrity:
    def test_faithful_paraphrase_clean(self):
        ledger = ClaimsLedger()
        c = _claim(ledger)  # keeps "associated with" and "sample"
        assert check_modality(c) == []

    def test_causal_inflation_flagged(self):
        ledger = ClaimsLedger()
        c = _claim(ledger, paraphrase="Adapted CBT causes symptom reduction in people.")
        checks = {f.check for f in check_modality(c)}
        assert "causal_or_scope_inflation" in checks

    def test_hedge_loss_flagged(self):
        span = _span(text="The findings suggest that engagement may improve outcomes.")
        ledger = ClaimsLedger()
        c = _claim(ledger, paraphrase="Engagement improves outcomes.", evidence=[span])
        assert any(f.check == "qualification_loss" for f in check_modality(c))

    def test_clinical_recommendation_by_inference_flagged(self):
        ledger = ClaimsLedger()
        _claim(ledger, ctype="clinical_recommendation", status="editorial_inference",
               paraphrase="Therapists should extend session counts.")
        flags = check_ledger_integrity(ledger)
        assert any(f.check == "clinical_inference" for f in flags)

    def test_duplicate_paraphrase_flagged(self):
        ledger = ClaimsLedger()
        _claim(ledger)
        _claim(ledger)
        flags = check_ledger_integrity(ledger)
        assert any(f.check == "duplicate_paraphrase" for f in flags)


class TestTrace:
    def test_trace_resolves_claim(self, tmp_path):
        staged = tmp_path / "skill"
        (staged / "provenance").mkdir(parents=True)
        (staged / "chapters").mkdir()
        ledger = ClaimsLedger()
        c = _claim(ledger)
        ledger.save(staged / "provenance" / "claims.jsonl")
        (staged / "provenance" / "sources.json").write_text(json.dumps([{
            "source_id": "SRC-abc123", "title": "Cultural Adaptation of CBT",
            "authors": ["A. Author"], "edition": "2nd", "year": 2021,
            "bibliographic_id": "isbn:978-x", "citation_key": "BOOK1",
        }]), encoding="utf-8")
        (staged / "chapters" / "ch04.md").write_text(
            f"Claim text. [CLM:{c.claim_id}]", encoding="utf-8")

        result = trace_claim(staged, c.claim_id)
        assert result["source"]["title"] == "Cultural Adaptation of CBT"
        assert result["cited_in"] == ["chapters/ch04.md"]
        assert result["evidence"][0]["text"].startswith("Culturally adapted CBT")

    def test_trace_verifies_against_source_text(self, tmp_path):
        staged = tmp_path / "skill"
        (staged / "provenance").mkdir(parents=True)
        passage = "The exact supporting passage."
        ledger = ClaimsLedger()
        c = _claim(ledger, evidence=[EvidenceSpan(
            source_id="SRC-abc123", start_char=0, end_char=len(passage), text=passage)])
        ledger.save(staged / "provenance" / "claims.jsonl")
        good = trace_claim(staged, c.claim_id, {"SRC-abc123": passage})
        assert good["evidence"][0]["matches_recorded"] is True
        bad = trace_claim(staged, c.claim_id, {"SRC-abc123": "Tampered text here!!!!!!!"})
        assert bad["evidence"][0]["matches_recorded"] is False

    def test_trace_missing_claim_raises(self, tmp_path):
        staged = tmp_path / "skill"
        (staged / "provenance").mkdir(parents=True)
        ClaimsLedger().save(staged / "provenance" / "claims.jsonl")
        with pytest.raises(KeyError):
            trace_claim(staged, "CLM-999999")
