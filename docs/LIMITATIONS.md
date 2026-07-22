# Limitations and disclaimers

## What this system does and does not claim

This system is **source-grounded and traceable**: it is designed to reduce
unsupported generation and to make what remains auditable. It does **not**
eliminate hallucination. A model can still misread a passage it cites; the
citation makes that checkable, not impossible.

## Scholarly and clinical use disclaimer

Generated skills are reference artifacts derived from the supplied sources.

- **Clinical profiles** (clinical-method, cbt-manual, clinical-trial):
  outputs are educational reference material. They are not clinical advice,
  not a treatment manual substitute, and never a basis for patient-specific
  decisions. Clinical use of the underlying methods requires training,
  competence, and supervision as the source materials themselves specify.
- **Policy profile**: outputs are reference material, not legal advice.
- **Invention profile**: outputs never constitute patent novelty or
  freedom-to-operate conclusions.

## Known technical limitations

- **Injection detection is deterministic pattern matching** (Layers A/B).
  A novel phrasing can evade it. The design compensates with capability
  minimisation (generated skills are read-only), output scanning, and
  mandatory human review — detection is a filter, not the trust boundary.
- **Extractors are not sandboxed.** pdftotext, ebook-convert and friends
  parse untrusted files with native code. Convert hostile documents inside
  a container/VM.
- **Identifier detection is pattern-based and incomplete.** The
  clinical-restricted redaction report is input to human review, not a
  guarantee of de-identification. Do not rely on it as the only control
  for participant-identifiable material.
- **Modality checks are lexical heuristics.** They flag common inflation
  patterns; they do not certify semantic fidelity. The review packet
  exists because these checks are incomplete.
- **Chapter detection can fail** on unconventional structures; use
  `--structure-map`. Sentence-level structure nodes, first-class
  table/figure objects beyond markdown, and cross-document trial
  inconsistency *detection* (the schema exists; the comparator does not)
  are deferred — see FORK_ARCHITECTURE_PLAN.md.
- **Citation coverage measures markers, not truth.** Coverage ≥ 0.98 with
  correctness ≥ 0.95 still leaves room for a cited-but-misread claim;
  that residue is what expert review is for.

## Copyright

The pipeline synthesises rather than reproduces (evidence spans are
bounded; long verbatim reproduction is flagged), and generated metadata
records each source's privacy classification. This is hygiene, not legal
clearance: converting a work you do not own, for uses beyond personal
reference, remains your responsibility to assess.
