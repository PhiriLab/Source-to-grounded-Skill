# Threat model

Scope: the conversion pipeline (documents in → generated agent skill out),
the generated skill as a persistent prompt artifact, and the data handled
along the way.

## Assets

1. **The host agent's future behaviour.** A generated skill is a prompt the
   agent will obey in later sessions. Corrupting it is persistent prompt
   injection.
2. **The user's machine and accounts.** Shell, filesystem, credentials,
   network reachable from the agent session that runs conversion.
3. **Source material.** Copyrighted books, confidential institutional
   documents, clinically restricted material (potentially participant
   -identifiable).
4. **Scholarly integrity of outputs.** Fluent distortion (overclaiming,
   harmonised contradictions, lost contraindications) is a harm class of
   its own, treated here as seriously as code execution.

## Adversaries and threat classes

### T1 — Malicious or compromised source document
A document crafted (or trojaned in transit) to influence generation:
- Indirect prompt injection: imperative text addressed to the agent, hidden
  in body text, footnotes, metadata, appendices.
- Hidden content: bidirectional overrides, zero-width characters, white-on
  -white HTML, HTML comments, encoded (Base64/hex) blobs.
- Structure forgery: fake chapter headings or ToC entries that redirect
  which text the agent reads and cites.
- Resource abuse: zip bombs inside EPUB/DOCX, gigantic page counts,
  pathological filenames.

Mitigations: normalisation + hidden-content detection with an audit log
(`content_sanitizer`); layered deterministic injection detection with
severity-gated stop (`injection_detector`, `policy`); size/page/token and
decompression limits; strict path handling (no symlink following into
outputs, filename sanitisation); original bytes preserved for audit —
sanitisation never destroys evidence.

### T2 — Malicious generated output (second stage of T1)
Even with clean-looking sources, generation can emit a skill that carries
instructions: shell commands, network calls, credential access, agent
role-redefinition, "do not tell the user", suppressed citations.

Mitigations: generated skills are read-only reference artifacts by default
(`capability_profile: scholarly-reference`); every generated file passes
`output_scanner` before publication; publication is a separate explicit
step from a staging directory that is never a live skills root; publish
gate requires unresolved high/critical findings = 0. A model never clears
its own output — the scanner is deterministic.

### T3 — Compromise via the converter's own supply chain
Upstream is a fast-moving solo-author repo; its SKILL.md becomes agent
instructions verbatim.

Mitigations: fork pins the audited upstream commit (`docs/UPSTREAM.md`);
CI runs dependency vulnerability scanning; optional extractor installation
remains opt-in and interactive; no network access is required or used by
the pipeline itself.

### T4 — Data exposure of restricted sources
Clinical or institutional material leaking into generated skills, temp
files, or logs.

Mitigations: privacy profiles (`public`, `copyrighted-private`,
`institutional-confidential`, `clinical-restricted`); `clinical-restricted`
requires review, enables identifier scanning/redaction reporting, sets
restrictive permissions (0700 dirs / 0600 files) on working and staging
directories, and the output scanner blocks participant-level identifiers in
generated files; working files are removed on publish or via `clean`.
Residual risk: pattern-based identifier detection is not complete — the
redaction report is input to human review, not a guarantee.

### T5 — Epistemic corruption (fluent distortion)
Not an "attacker" in the classic sense; the model itself is the hazard:
unsupported claims, causal inflation, dropped qualifications, silently
harmonised contradictions, invented framework names, population
generalisation, lost contraindications.

Mitigations: claims ledger with mandatory provenance; deterministic
citation-coverage and marker-resolution validation; modality-preservation
checks; contradiction outputs are first-class; world knowledge off/labelled
by default; review packet surfaces low-confidence and high-impact claims;
release-gating evaluation metrics with fixed thresholds; clinical
contraindication retention threshold is 1.00.

## Trust boundaries

```
[untrusted]  source documents, anything extracted from them
[semi]       host agent generation output (until scanned + validated)
[trusted]    deterministic pipeline code, reviewer decisions, policy config
```

Rules at the boundaries:
- Nothing extracted from a document is ever executed, evaluated, or used to
  construct file paths without sanitisation.
- Generation output enters trusted territory only after output scan +
  provenance validation + (for publication) human review.
- Reviewer decisions are the highest authority and are keyed to evidence
  content hashes so they cannot silently apply to changed text.

## Non-goals / residual risks

- A determined novel injection phrased to evade all deterministic patterns
  may pass Layers A/B; the design compensates with capability minimisation
  (a read-only skill that is obeyed still cannot execute anything) and human
  review before publication. Detection is a filter, not the boundary.
- The pipeline does not sandbox the extractors themselves (pdftotext,
  ebook-convert parse untrusted files with C code); users processing hostile
  documents should run conversion in a container/VM. Documented in
  LIMITATIONS.md.
- No claim is made that hallucination is eliminated. The system is
  source-grounded and traceable, designed to reduce unsupported generation
  and to make what remains auditable.
