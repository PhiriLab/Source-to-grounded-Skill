"""Tests for declarative domain profiles and their loader guarantees."""

import pytest

from book_to_skill.profiles import (
    PROFILE_NAMES,
    Profile,
    ProfileError,
    OutputSpec,
    _validate,
    load_profile,
)


class TestAllProfiles:
    @pytest.mark.parametrize("name", PROFILE_NAMES)
    def test_loads_and_validates(self, name):
        p = load_profile(name)
        assert p.name == name
        assert p.description
        assert "SKILL.md" in p.required_files
        assert "provenance/claims.jsonl" in [o.file for o in p.outputs]
        assert p.constraints, f"{name} must declare constraints"

    @pytest.mark.parametrize("name", PROFILE_NAMES)
    def test_generated_skills_are_read_only(self, name):
        perms = load_profile(name).capability_profile["permissions"]
        assert perms["read_skill_files"] is True
        for risky in ("shell", "network", "write_files", "access_secrets"):
            assert perms[risky] is False

    @pytest.mark.parametrize("name", PROFILE_NAMES)
    def test_no_profile_defaults_to_unrestricted_knowledge(self, name):
        wk = load_profile(name).defaults.get("world_knowledge", "off")
        assert wk in ("off", "labelled")

    @pytest.mark.parametrize("name", PROFILE_NAMES)
    def test_review_required_by_default(self, name):
        assert load_profile(name).defaults.get("require_review") is True


class TestSpecificCommitments:
    def test_clinical_profiles_strict_and_offline(self):
        for name in ("clinical-method", "cbt-manual", "clinical-trial"):
            p = load_profile(name)
            assert p.defaults["security"] == "strict"
            assert p.defaults["world_knowledge"] == "off"

    def test_clinical_profiles_keep_contraindications(self):
        for name in ("clinical-method", "cbt-manual"):
            p = load_profile(name)
            assert "contraindications.md" in p.required_files
            assert any("patient-specific" in c for c in p.constraints)

    def test_cultural_adaptation_refuses_trait_inference(self):
        p = load_profile("cultural-adaptation")
        joined = " ".join(p.constraints)
        assert "nationality" in joined
        assert "fixed group traits" in joined
        assert "deep-structure adaptation" in p.analytical_dimensions

    def test_gmh_dimensions_are_analytical(self):
        p = load_profile("global-mental-health")
        assert "whose categories are being universalised" in p.analytical_dimensions
        assert len(p.analytical_dimensions) >= 6

    def test_trial_profile_reports_inconsistencies(self):
        p = load_profile("clinical-trial")
        assert "inconsistencies.md" in p.required_files
        assert "trial-structured.json" in p.required_files

    def test_research_cluster_forbids_pooling(self):
        p = load_profile("research-cluster")
        assert any("pooling" in c for c in p.constraints)
        assert "study-matrix.csv" in p.required_files

    def test_invention_profile_forbids_patent_conclusions(self):
        p = load_profile("invention-and-design")
        assert any("patent" in c for c in p.constraints)

    def test_scholarly_book_preserves_contradictions(self):
        p = load_profile("scholarly-book")
        assert "contradictions.md" in p.required_files
        assert "scope-and-limitations.md" in p.required_files


class TestLoaderGuards:
    def _mk(self, **kw):
        base = dict(
            name="scholarly-book", description="d",
            outputs=[OutputSpec(file="SKILL.md", purpose="p"),
                     OutputSpec(file="provenance/claims.jsonl", purpose="p")],
            constraints=["c"],
        )
        base.update(kw)
        return Profile(**base)

    def test_unknown_profile_name(self):
        with pytest.raises(ProfileError, match="unknown profile"):
            _validate(self._mk(name="astrology"))

    def test_unrestricted_default_rejected(self):
        with pytest.raises(ProfileError, match="unrestricted"):
            _validate(self._mk(defaults={"world_knowledge": "unrestricted"}))

    def test_risky_capability_rejected(self):
        with pytest.raises(ProfileError, match="shell"):
            _validate(self._mk(capability_profile={"permissions": {"shell": True}}))

    def test_missing_skill_md_rejected(self):
        with pytest.raises(ProfileError, match="SKILL.md"):
            _validate(self._mk(outputs=[OutputSpec(file="notes.md", purpose="p")]))

    def test_nonexistent_file_load(self):
        with pytest.raises(ProfileError, match="no such profile"):
            load_profile("does-not-exist")
