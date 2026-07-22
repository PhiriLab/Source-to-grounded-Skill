# source-to-grounded-skill

**A provenance-preserving scholarly knowledge compiler.** Converts books,
papers, clinical manuals, trial documents, and policy texts (PDF, EPUB,
DOCX, HTML, Markdown, plain text, RTF, MOBI/AZW via Calibre) into agent
skills in which **every substantive claim remains traceable to an
identifiable source passage** — with security scanning of the documents,
staged output, claim-level citations, human review states, and
release-gating evaluation.

Fork of [virgiliojr94/book-to-skill](https://github.com/virgiliojr94/book-to-skill)
(baseline `68888e9`; see [docs/UPSTREAM.md](docs/UPSTREAM.md)). The upstream
extraction machinery is preserved and still works unchanged; what changed
is everything between extraction and installation.

## The governing rule

> Every substantive generated claim must remain traceable to an
> identifiable source passage, and every synthesis must declare whether it
> is quoted, paraphrased, inferred, contested, or externally supplemented.

The system is source-grounded and traceable, designed to reduce unsupported
generation. It does not claim to eliminate hallucination — it makes the
residue auditable ([docs/LIMITATIONS.md](docs/LIMITATIONS.md)).

## Pipeline

```
source files
  → extraction                     (upstream parsers)
  → sanitisation                   (NFC, bidi/zero-width removal, audit log;
                                    originals preserved verbatim)
  → injection scan                 (layered, deterministic; severity gates)
  → staged corpus                  (.book-to-skill/staging/<skill-id>/ —
                                    never a live skills directory)
  → claims ledger + skill files    (host agent, per SKILL.md: evidence spans
                                    with exact offsets, [SRC:...] citations)
  → validate                       (ledger re-hashed against sources, marker
                                    resolution, output security scan, REVIEW.md)
  → human review                   (approve/reject per claim; decisions
                                    survive regeneration unless evidence changed)
  → publish                        (explicit, deterministically gated)
```

## Quick start

```bash
pip install .                      # installs source-to-skill (and book-to-skill)

source-to-skill convert book.pdf --skill-id my-book --profile scholarly-book --output .
# ... host agent (Claude Code / Copilot CLI / Amp) generates per SKILL.md ...
source-to-skill validate .book-to-skill/staging/my-book
source-to-skill review   .book-to-skill/staging/my-book
source-to-skill trace CLM-000001 --skill .book-to-skill/staging/my-book
source-to-skill approve CLM-000001 --skill .book-to-skill/staging/my-book --reviewer you
source-to-skill mark-reviewed .book-to-skill/staging/my-book --reviewer you
source-to-skill publish .book-to-skill/staging/my-book --to ~/.claude/skills
```

`source-to-skill scan|inspect|diff|evaluate|profiles` round out the CLI.
Plain `book-to-skill <paths>` (upstream extraction) still works.

## Domain profiles

Declarative YAML under `book_to_skill/profiles/`, selected with
`--profile`: `scholarly-book`, `clinical-method`, `cbt-manual`,
`global-mental-health`, `cultural-adaptation`, `clinical-trial`,
`research-cluster`, `teaching-and-supervision`,
`policy-and-implementation`, `invention-and-design`.

Each profile fixes output files, preservation commitments, and hard
constraints (e.g. clinical profiles require a contraindications file and
forbid patient-specific recommendations; the cultural-adaptation profile
forbids inferring culture from nationality; no profile may grant a
generated skill shell, network, write, or secrets access).

## Security model, in one paragraph

Documents are untrusted input; generated skills are persistent prompts.
Both cross deterministic scanners with severity-gated stops, generation
happens only in a private staging area, generated skills are read-only
reference artifacts, and publication requires passing a gate no model can
override. Detection is a filter, not the trust boundary — capability
minimisation and human review carry the residual risk. Full model:
[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md),
[docs/PRIVACY_MODEL.md](docs/PRIVACY_MODEL.md).

## Documentation

| Doc | What it covers |
|---|---|
| [docs/FORK_ARCHITECTURE_PLAN.md](docs/FORK_ARCHITECTURE_PLAN.md) | design, amendments to the original spec, deferred work |
| [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) | assets, threat classes, trust boundaries, residual risks |
| [docs/PROVENANCE_SPEC.md](docs/PROVENANCE_SPEC.md) | entities, ledger, citation grammar, modality rules |
| [docs/REVIEW_GUIDE.md](docs/REVIEW_GUIDE.md) | reviewer workflow and decision persistence |
| [docs/PRIVACY_MODEL.md](docs/PRIVACY_MODEL.md) | privacy classifications and their enforcement |
| [docs/MIGRATION_FROM_UPSTREAM.md](docs/MIGRATION_FROM_UPSTREAM.md) | what changed, what didn't, migrating old skills |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | disclaimers and known limits — read before clinical/scholarly use |

## Evaluation

`evaluation/` ships release-gating metrics (citation coverage ≥ 0.98,
citation correctness ≥ 0.95, unsupported claims ≤ 0.01, injection recall
≥ 0.95, contraindication retention = 1.00, causal inflation ≤ 0.02) and an
adversarial corpus (hidden instructions, footnote injections, bidi and
zero-width tricks, hidden CSS, benign controls). Run against a staged
skill: `source-to-skill evaluate <staging-dir>`. No security or
clinical-safety test is marked expected-failure.

## Credit and license

Upstream book-to-skill by [@virgiliojr94](https://github.com/virgiliojr94)
— the extraction pipeline, multilingual chapter detection, and the
token-efficiency philosophy carry over. MIT, as upstream
([LICENSE.md](LICENSE.md)).
