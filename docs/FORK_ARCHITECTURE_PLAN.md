# Fork architecture plan — source-to-grounded-skill

Status: living document. Maps the fork objective onto the actual upstream
repository structure, records deliberate amendments to the original
specification, and defines the first usable milestone.

## Fork objective

Evolve `book-to-skill` (a general document-to-agent-skill converter) into a
**provenance-preserving scholarly knowledge compiler**. The governing rule:

> Every substantive generated claim must remain traceable to an identifiable
> source passage, and every synthesis must declare whether it is quoted,
> paraphrased, inferred, contested, or externally supplemented.

Primary materials: authored scholarly books, academic papers, clinical trial
documents, CBT and psychotherapy manuals, global mental health texts,
cross-cultural frameworks, teaching materials, policy documents,
methodological work, and invention/design notes.

## Upstream reality (what the code actually does)

Upstream at `68888e9` (see `docs/UPSTREAM.md`) is:

- `book_to_skill/` — extraction package: format detection (suffix + magic
  bytes), per-format parsers (PDF/EPUB/DOCX/HTML/RTF/text/Calibre), chapter
  heading detection (Arabic/Roman/CJK numerals, ATX/setext headings), token
  estimation, opt-in dependency installation.
- Output: `full_text.txt` (all sources concatenated with `SOURCE:` banners)
  and `metadata.json` in `$BOOK_SKILL_WORKDIR` (default
  `<tempdir>/book_skill_work`).
- `SKILL.md` — the operative artifact: instructions the **host agent**
  (Claude Code / Copilot CLI / Amp) follows to analyse the extracted text and
  generate the skill files directly into a live skills directory
  (`~/.claude/skills/...`).
- `tools/validate_skill.py` — post-hoc structural checks on a generated
  skill.
- No security boundary between document content and generation; no
  provenance; generation writes straight into live skill roots; all
  epistemic responsibility sits in free-form agent instructions.

**Key architectural fact** that shapes everything below: *generation is
performed by the host agent, not by Python code*. The Python package only
extracts. Therefore the fork's guarantees must be enforced by:

1. **Deterministic Python stages** wherever mechanically checkable
   (sanitisation, injection scanning, staging, output scanning, citation
   resolution, ledger validation, review gates) — a model is never the sole
   authority for security clearance or publication.
2. **Rewritten SKILL.md instructions** for what only the model can do
   (claim extraction, paraphrase, synthesis) — always emitting artifacts the
   deterministic validators can then check (claims ledger, citation
   markers).

## Amendments to the original specification

These are deliberate deviations, made for usability and honesty about what
the architecture can enforce:

1. **Branch**: work proceeds on the session's designated branch
   (`claude/book-to-skill-security-xxklyq`), not
   `feat/grounded-scholarly-compiler`.
2. **Package name is kept** as `book_to_skill` for import compatibility and
   a clean upstream diff; the *product* identity becomes
   source-to-grounded-skill. A `source-to-skill` console script is added
   alongside `book-to-skill`.
3. **First milestone over full surface**: per the specification's own
   closing recommendation, the first usable milestone is one public-domain
   book converted under the `scholarly-book` profile with claim-level
   provenance, security scanning, staged generation, review states, and a
   measurable evaluation report. The other nine profiles ship as declarative
   YAML riding the same machinery, not as bespoke code paths.
4. **Claim anchoring**: v1 anchors claims to `(source_id, section_id,
   char_start, char_end)` against the preserved original extraction, plus
   printed-page numbers where the extractor exposes them. The full
   Book→Part→…→Sentence tree is represented as far as detection allows
   (parts/chapters/sections); sentence-level nodes are deferred — offsets
   already give sentence-precision addressing without the tree.
5. **Classifier layer (Layer C) of injection detection is an interface
   only** in v1; deterministic Layers A and B gate. This honours "never make
   a model the sole authority for security clearance" — a model layer can
   only *raise* severity, never lower it.
6. **PII redaction** in `clinical-restricted` privacy mode is
   pattern-based (names excepted) and produces a findings report for human
   action; it does not claim completeness. Participant-level material is
   blocked from generated skills by the output scanner, not by trusting
   redaction.
7. **Semantic diff / fold-in invalidation** is implemented at the claim
   level (hash of supporting span → claim invalidated when the span's
   content hash changes), not as general semantic diffing.

## Target pipeline

```
source files
  → extraction (upstream parsers, unchanged)
  → normalisation + sanitisation        [security/content_sanitizer]
      original bytes and text preserved; sanitised analysis copy + log
  → injection scan                      [security/injection_detector]
      findings gate: high/critical stops generation (policy)
  → quarantined source corpus           [staging dir, per-source originals]
  → structured evidence extraction      [host agent, per SKILL.md]
  → claims ledger + generated files     [host agent → staging only]
  → generated-output scan               [security/output_scanner]
  → deterministic validation            [provenance validator, citation
                                         coverage, modality checks]
  → REVIEW.md + human review            [review/]
  → publish (explicit)                  [copies staging → skills root]
```

Staging root: `<output>/.source-to-skill/staging/<skill-id>/` (never a live
agent skills directory). Publication is a separate, explicit, gated step.

## Module map

```
book_to_skill/
    security/
        __init__.py
        findings.py            # SecurityFinding, severity, categories, JSONL
        content_sanitizer.py   # NFC, bidi/zero-width detection, hidden text,
                               # encoded blobs, HTML comments; transform log
        injection_detector.py  # Layer A patterns + Layer B structural
        output_scanner.py      # generated-markdown scanner (shell/network/
                               # credential/identity/disclosure patterns)
        policy.py              # risk → action mapping, security modes
    provenance/
        __init__.py
        models.py              # Source, DocumentSection, EvidenceSpan, Claim,
                               # Citation, ReviewDecision, GenerationManifest
        ids.py                 # stable IDs (content-derived, prefix-typed)
        ledger.py              # JSONL claims ledger read/write/validate
        citations.py           # [SRC:...] marker grammar, parse + resolve
        trace.py               # claim → source passage resolution
    review/
        __init__.py
        state.py               # skill states + transition rules
        packet.py              # REVIEW.md generation
        decisions.py           # approve/reject/annotate, persistence keyed
                               # to evidence-span content hash
    profiles/
        __init__.py            # loader + validation
        *.yaml                 # 10 declarative domain profiles
    staging.py                 # staging layout, install/publish
    cli.py                     # subcommand CLI (kept back-compatible)
evaluation/
    fixtures/adversarial/      # injection, unicode, forged-heading corpora
    gold/                      # gold claims for a public-domain sample
    metrics.py                 # citation coverage/correctness, unsupported
                               # rate, qualification retention, detection recall
docs/
    THREAT_MODEL.md
    PROVENANCE_SPEC.md
    REVIEW_GUIDE.md
    MIGRATION_FROM_UPSTREAM.md
    LIMITATIONS.md
```

## Epistemic model (summary; normative text in PROVENANCE_SPEC.md)

- Claims ledger: JSONL, one claim per line, stable `CLM-` IDs.
- Epistemic statuses: `direct_quotation`, `close_paraphrase`,
  `author_position`, `empirical_finding`, `methodological_recommendation`,
  `clinical_recommendation`, `cross_source_synthesis`, `editorial_inference`,
  `external_contextualisation`, `reviewer_annotation`, `contested_claim`,
  `uncertainty_or_limitation`.
- Citation marker grammar: `[SRC:<source>:<section>:<locator>]`, resolvable
  by `source-to-skill trace`.
- World knowledge: `off` by default for scholarly/clinical profiles;
  `labelled` renders under an explicit "External context" voice; never
  presented as originating in the sources.
- Contradiction preservation: contradictions are first-class outputs
  (`contradictions.md`), never silently harmonised.
- Modality preservation: deterministic checks flag hedge-to-assertion
  drift ("may" → "does", "suggests" → "demonstrates", population widening).

## Review and publication

States: `draft → security-cleared → source-verified → expert-reviewed →
published` (+ `deprecated`). Generation always lands in `draft`.
`publish` refuses unless: no unresolved high/critical security findings,
citation validation passes, and the state gate for the requested target is
met (or the user explicitly overrides with a recorded reason).
Reviewer decisions persist across regeneration keyed to the content hash of
the supporting evidence span; a changed span invalidates the decision.

## Evaluation

Metrics that gate release (thresholds recorded in `evaluation/metrics.py`):
citation coverage ≥ 0.98, citation correctness ≥ 0.95, unsupported
substantive claims ≤ 0.01, high-risk injection detection recall ≥ 0.95,
clinical contraindication retention = 1.00. Security and clinical-safety
tests are never marked expected-failure.

## Deferred (recorded, not forgotten)

- Layer C model-assisted injection classification (interface stubbed).
- Sentence-level structure nodes; docling-based table/figure first-class
  objects beyond markdown preservation.
- Host-specific capability manifests beyond the generated
  `capability_profile` block.
- Registry/protocol/SAP cross-document inconsistency detection for the
  clinical-trial profile (schema shipped; comparator logic deferred).
- Archive-bomb limits apply to EPUB/DOCX zip payloads; other archive
  formats are out of scope (not accepted inputs).
