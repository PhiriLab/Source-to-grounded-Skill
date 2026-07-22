"""Deterministic epistemic-integrity checks.

Compare a claim's generated paraphrase against its recorded evidence to flag
fluent distortion: hedges dropped, associations promoted to causes, study
populations widened to "people", suggestion inflated to demonstration.

These are lexical heuristics, deliberately conservative: they *flag for
review*, they do not prove distortion. A model may be layered on later, but
per the trust rules a model can only add flags, never clear these.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from book_to_skill.provenance.models import Claim

_HEDGES = (
    "may", "might", "could", "can", "suggests", "suggest", "appears",
    "appeared", "seems", "seemed", "possibly", "probably", "likely",
    "preliminary", "tentative", "in this context", "in this study",
    "in this sample", "associated with", "correlated with", "some",
    "sometimes", "often", "clinical observation", "hypothesis",
)

# (evidence-side pattern, paraphrase-side pattern, label)
_INFLATIONS: list[tuple[re.Pattern, re.Pattern, str]] = [
    (re.compile(r"\bassociated with\b|\bcorrelat\w+ with\b", re.I),
     re.compile(r"\bcauses?\b|\bleads? to\b|\bresults? in\b|\bproduces?\b", re.I),
     "association promoted to causation"),
    (re.compile(r"\bsuggests?\b|\bindicat\w+\b|\bappears? to\b", re.I),
     re.compile(r"\bdemonstrates?\b|\bproves?\b|\bshows? conclusively\b|\bestablishes\b", re.I),
     "suggestion inflated to demonstration"),
    (re.compile(r"\bparticipants?\b|\bpatients? in\b|\bthis sample\b|\bthe sample\b", re.I),
     re.compile(r"\bpeople\b|\beveryone\b|\ball patients\b|\bindividuals in general\b", re.I),
     "study population generalised"),
    (re.compile(r"\bsome\b|\ba minority of\b|\bseveral\b", re.I),
     re.compile(r"\bmost\b|\bthe majority\b|\ball\b|\balways\b", re.I),
     "quantifier widened"),
    (re.compile(r"\bclinical observation\b|\bcase reports?\b|\banecdot\w+\b", re.I),
     re.compile(r"\bevidence shows\b|\btrial evidence\b|\bempirical(?:ly)? support\w*\b", re.I),
     "observation promoted to evidence"),
    (re.compile(r"\bin this (?:context|setting|population|study|trial)\b", re.I),
     re.compile(r"\bin general\b|\buniversal\w*\b|\bacross (?:all )?(?:settings|cultures|populations)\b", re.I),
     "contextual claim universalised"),
]


@dataclass
class IntegrityFlag:
    claim_id: str
    check: str
    detail: str


def _evidence_text(claim: Claim) -> str:
    return " ".join(span.text for span in claim.evidence)


def check_modality(claim: Claim) -> list[IntegrityFlag]:
    """Flag hedge loss and known inflation patterns for one claim."""
    flags: list[IntegrityFlag] = []
    if not claim.evidence:
        return flags
    evidence = _evidence_text(claim).lower()
    paraphrase = claim.paraphrase.lower()

    for ev_pat, para_pat, label in _INFLATIONS:
        if ev_pat.search(evidence) and para_pat.search(paraphrase) and not para_pat.search(evidence):
            flags.append(IntegrityFlag(claim.claim_id, "causal_or_scope_inflation", label))

    ev_hedges = {h for h in _HEDGES if re.search(rf"\b{re.escape(h)}\b", evidence)}
    para_hedges = {h for h in _HEDGES if re.search(rf"\b{re.escape(h)}\b", paraphrase)}
    if ev_hedges and not para_hedges:
        flags.append(IntegrityFlag(
            claim.claim_id,
            "qualification_loss",
            f"evidence hedges ({', '.join(sorted(ev_hedges)[:4])}) absent from paraphrase",
        ))
    return flags


def check_ledger_integrity(claims) -> list[IntegrityFlag]:
    """Run modality checks over an iterable of claims; add structural checks."""
    flags: list[IntegrityFlag] = []
    seen_paraphrases: dict[str, str] = {}
    for claim in claims:
        flags.extend(check_modality(claim))
        # Clinical recommendations must carry either an uncertainty partner
        # or explicit evidence — never stand as bare editorial synthesis.
        if claim.claim_type == "clinical_recommendation" and claim.epistemic_status == "editorial_inference":
            flags.append(IntegrityFlag(
                claim.claim_id, "clinical_inference",
                "clinical recommendation carried by editorial inference — needs source support or reviewer sign-off",
            ))
        key = " ".join(claim.paraphrase.lower().split())
        if key in seen_paraphrases:
            flags.append(IntegrityFlag(
                claim.claim_id, "duplicate_paraphrase",
                f"duplicates {seen_paraphrases[key]}",
            ))
        else:
            seen_paraphrases[key] = claim.claim_id
    return flags
