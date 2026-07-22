# Provenance specification

Normative for generated skills. Enforced by `source-to-skill validate` and
the evaluation harness; the SKILL.md instructions implement it.

## Entities

Defined in `book_to_skill/provenance/models.py`:

| Entity | ID form | Identity |
|---|---|---|
| Source | `SRC-<sha256[:12]>` | content-derived (file hash) |
| DocumentSection | `SEC-<citation_key>-<label>` | structural position |
| EvidenceSpan | (embedded in claim) | `content_hash` = sha256 of whitespace-normalised text |
| Claim | `CLM-<6 digits>` | ledger-sequential |
| ReviewDecision | keyed by claim id | `evidence_hash` binds it to the passage reviewed |
| GenerationManifest | one per staged skill | — |

Content-derived source/section IDs mean regeneration over unchanged sources
yields identical IDs, which is what lets reviewer decisions survive
regeneration (see REVIEW_GUIDE.md).

## The claims ledger

`provenance/claims.jsonl` — one claim per line, the source of truth for all
substantive generated content. Generated Markdown is downstream of the
ledger and must not introduce substantive content the ledger doesn't carry.

Claim fields: see SKILL.md Step 3 for the authoring contract and
`models.py` for the schema. Two rules are structural, not stylistic:

1. Every epistemic status except `external_contextualisation` and
   `reviewer_annotation` **requires** at least one evidence span.
2. `external_contextualisation` must have an empty `source_id` — external
   knowledge is never attributed to a source.

### Evidence spans

- `(source_id, start_char, end_char)` address the **preserved original
  extraction** (`provenance/sources/<SRC-id>.txt`), not the sanitised copy.
- `text` must equal the addressed range; `validate` re-hashes it. A
  citation that is present but wrong fails validation.
- Spans over 1,200 characters are flagged: evidence supports, it does not
  reproduce (copyright hygiene).

## Epistemic statuses

`direct_quotation`, `close_paraphrase`, `author_position`,
`empirical_finding`, `methodological_recommendation`,
`clinical_recommendation`, `cross_source_synthesis`, `editorial_inference`,
`external_contextualisation`, `reviewer_annotation`, `contested_claim`,
`uncertainty_or_limitation`.

The five rendered voices map onto these: source statement (quotation /
author_position / empirical_finding), close paraphrase, synthesis
(cross_source_synthesis / editorial_inference), external context
(external_contextualisation, only under `world_knowledge: labelled`),
reviewer annotation.

## Citation markers

Grammar (parser in `provenance/citations.py`):

```
[SRC:<source-key>:<section-label>:<locator>]   locator = P<start>[-<end>] pages
                                                       | C<start>[-<end>] chars
[SRC:<source-key>:<section-label>]
[CLM:CLM-<n>]
```

Every substantive paragraph (≥ 80 chars, not a heading/table/code/scaffold
line) must carry at least one resolvable marker. Coverage is release-gated
at ≥ 0.98; marker resolution failures block publication.

## Modality preservation

The paraphrase keeps the evidence's hedges and scope. Deterministic checks
(`provenance/integrity.py`) flag: association→causation,
suggestion→demonstration, study-population→"people", quantifier widening,
observation→evidence, contextual→universal, and wholesale hedge loss.
Flags route to the review packet; a model may add flags but never clear
them.

## Tracing

`source-to-skill trace CLM-000481 --skill <dir>` resolves a claim to its
bibliographic source, evidence spans (verified live against the preserved
text), review status, and the generated files citing it.
