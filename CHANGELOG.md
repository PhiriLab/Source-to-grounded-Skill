# Changelog

All notable changes to **book-to-skill** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Packaging: name the wheel package explicitly
  (`[tool.hatch.build.targets.wheel] packages = ["book_to_skill"]`) so
  `pip install .` works after the distribution rename — hatchling's
  default heuristic looked for a `source_to_grounded_skill/` directory
  and failed.

### Changed
- CI now triggers on pushes to `main` (the new default branch), so the
  test/lint/security jobs run on direct pushes there, not only on PRs.

### Security / Privacy
- The working-artifact directories are now git-ignored by default
  (`.source-to-skill/`, the legacy `.book-to-skill/`, `output/`, `*.ocr.txt`,
  `*.source.pdf`). The converter writes preserved source text (including whole
  books) under its staging root; ignoring these by default prevents copyrighted
  or private source material from ever being committed to a shared repository.

### Changed
- The staging root is renamed from `.book-to-skill/` to `.source-to-skill/`
  so the working directory matches the product identity. Existing
  `.book-to-skill/` stages still resolve when passed by explicit path.
- Consolidated to a single console command, `source-to-skill`; the duplicate
  `book-to-skill` command was removed to avoid two names for one tool.

### Removed
- The committed CodeQL workflow (`.github/workflows/codeql.yml`); code
  scanning is now handled by GitHub's Default setup, and the committed
  workflow was redundant and still pinned to the old `master` branch.

## [2.0.0] — 2026-07-22 (fork: source-to-grounded-skill)

Fork of upstream book-to-skill at `68888e9`, transformed into a
provenance-preserving scholarly knowledge compiler.

### Added
- Security boundary: Unicode/hidden-content sanitisation with audit log,
  layered deterministic prompt-injection detection, generated-output
  scanning, severity-gated policy (quarantine at critical in every mode),
  private staging under `.book-to-skill/staging/` with path-escape and
  symlink protection.
- Provenance: claims ledger (JSONL) with evidence spans validated by
  re-hashing against preserved source text, twelve epistemic statuses,
  `[SRC:...]`/`[CLM:...]` citation grammar with coverage measurement,
  modality-preservation checks, `trace` from claim to passage.
- Review workflow: draft → security-cleared → source-verified →
  expert-reviewed → published states, REVIEW.md packet, claim-level
  approve/reject/annotate persisted across regeneration via evidence
  hashes, deterministic publication gate.
- Ten declarative domain profiles (scholarly, clinical, CBT, global
  mental health, cultural adaptation, clinical trial, research cluster,
  teaching, policy, invention) with loader-enforced non-negotiables.
- Subcommand CLI (`source-to-skill`): inspect, scan, convert, validate,
  trace, diff, review, approve/reject/annotate, mark-reviewed, publish,
  evaluate, profiles. Legacy `book-to-skill <paths>` extraction unchanged.
- Evaluation harness with fixed release thresholds and an adversarial
  corpus; `pyyaml` runtime dependency; hierarchical sectioning with
  YAML structure-map override.
- Documentation: threat model, privacy model, provenance spec, review
  guide, migration guide, limitations, fork architecture plan.

### Changed
- SKILL.md rewritten as grounded generation instructions (staging-only
  output, ledger-first, citations mandatory, world knowledge off by
  default, deterministic gates the agent must not bypass).
- Distribution renamed `source-to-grounded-skill` 2.0.0; import path
  `book_to_skill` unchanged.

### Removed
- Committed `scripts/__pycache__` bytecode.

### Documentation
- Clarified the two install paths so they are not confused: **`git clone` into a
  skills folder** registers the `/book-to-skill` agent skill (Claude Code / Copilot
  CLI / Amp), while **`pip install book-to-skill`** installs only the standalone
  extraction CLI and does not register the skill. README and the docs landing now
  show both explicitly.
- README now leads with the measured headline (24×–51× fewer tokens than a
  context-dump) and a 3-step "how it works", so the value lands in the first
  screen instead of being buried mid-page.

### Security
- **DOCX XXE / Billion Laughs hardening** — the DOCX extractor now scans the
  archive and rejects any XML part that declares a DTD or entities before
  parsing, blocking XML external-entity and entity-expansion attacks (#53, #54).
- **Subprocess argument-injection hardening** — file paths are absolutised
  before being passed to `pdftotext` / `pdfinfo` / `ebook-convert`, so a filename
  starting with `-` cannot be interpreted as a command-line option (#53, #54).
- **Dependency CVE review on pull requests** — a `dependency-review` CI job
  flags any newly introduced dependency carrying a moderate-or-higher CVE (or a
  denied license) and posts the findings as a PR comment. Dependabot now also
  covers the `pip` ecosystem.

### Changed
- **The `pdf` extra now installs `pypdf` instead of the deprecated `PyPDF2`**
  (`pip install book-to-skill[pdf]`). `pypdf` is the maintained successor;
  `PyPDF2` is end-of-life and no longer receives security fixes (#54).

### Fixed
- PDF text extracted via `pdftotext` is now decoded as UTF-8 rather than the
  process locale encoding, so accented characters and punctuation are no longer
  mojibake on non-UTF-8 locales (e.g. Windows).
- Text files (`.txt`, `.md`, `.rst`, `.adoc`, `.html`, `.rtf`) saved as UTF-16 or
  UTF-32 (e.g. Windows Notepad "Unicode" or PowerShell output) are now decoded by
  their byte-order mark instead of being read as `cp1252`/`latin-1` mojibake.
- The dependency-free RTF fallback (used when `striprtf` is not installed) now
  decodes `\uN` unicode escapes — smart quotes, dashes, accented letters — instead
  of dropping them and leaving only the ASCII fallback character.
- The stdlib HTML parser (the fallback for HTML files and EPUB extraction when
  BeautifulSoup is not installed) no longer decodes HTML entities twice, so
  double-encoded entities such as `&amp;amp;` survive intact.
- The dependency-free DOCX fallback (used when `python-docx` is not installed)
  now reconstructs tables as tab-joined rows in document order, instead of
  flattening each cell onto its own line.
- The dependency-free EPUB extractor (used when `ebooklib` is not installed) now
  reads content in true spine (reading) order instead of manifest order, so
  chapters are no longer scrambled. Content documents not listed in the spine are
  still included (appended after the spine content).

## [1.2.0] — 2026-06-17

### Added
- **Installable Python package.** The extractor is now a proper `book_to_skill`
  package with a `pyproject.toml` (hatchling build backend), a `book-to-skill`
  console script, and `python -m book_to_skill`. Optional extractors are exposed
  as extras (`epub`, `pdf`, `docx`, `rtf`, `technical`, `all`); the base install
  stays dependency-free with stdlib fallbacks. `requires-python = ">=3.9"`.
  `scripts/extract.py` is kept as a thin shim so the existing skill flow is
  unchanged (#34, #35, #48).
- **Markdown / AsciiDoc heading detection.** Structure detection recognizes ATX
  headings (`#`, `==`) as chapters when no numeric "Chapter N" headings are
  present, fixing a zero-chapter result for `.md` / `.adoc` sources. Headings
  inside fenced code blocks are ignored (#44).
- **setext / reStructuredText underline headings** — a title line over a row of
  `=` or `-` is now detected, so `.rst` and setext-style Markdown no longer
  report zero chapters. Guarded against thematic breaks, table borders, and YAML
  front matter (#51).
- **More chapter languages.** Chapter-word detection now covers French, German,
  Italian, and Dutch (`Chapitre`, `Kapitel`, `Capitolo`, `Hoofdstuk`), and
  heading titles starting with `Ü`/`Û`/`Ý`/`Þ` (e.g. "Überblick") are accepted (#49).
- **Multilingual table-of-contents detection** — Chinese, Japanese, French,
  German, Italian, and Dutch (#44).

### Fixed
- **Full-width Arabic digits in CJK chapter headings** — `第１章` (U+FF10–FF19),
  common in Japanese typesetting, is now detected like `第1章` (#46).
- **Parser errors are no longer swallowed silently.** Unexpected exceptions in
  any extractor are logged to stderr (extractor name + exception type) while the
  fallback chain still returns `None` and continues, so corrupt files and
  encoding errors are diagnosable (#47, #50).
- **All-punctuation ATX "titles"** (e.g. a `=====   =====` table border) are no
  longer miscounted as chapters (#51).
- **Package imports on interpreters that evaluate annotations eagerly.** Added
  `from __future__ import annotations` to every module using PEP 604 unions
  (`str | None`), so the package imports and runs cleanly on Python 3.9 (#34).

### Security
- **CI security scanning** — CodeQL (Python, security-and-quality + weekly
  schedule), Bandit (gates on HIGH severity; reports MEDIUM+ informationally),
  and Zizmor (GitHub Actions workflow audit, informational), plus a Dependabot
  config for the `github-actions` ecosystem. Known finding to harden next:
  Bandit B314 (`xml.etree.ElementTree.fromstring` in the DOCX parser).

### Changed
- CI test matrix now includes Python 3.9 so the import path above is guarded and
  cannot silently re-break.

## [1.1.0] — 2026-06-12

### Added
- **GitHub Copilot CLI as a first-class target** — the same `SKILL.md` now
  discovers, installs, and runs across GitHub Copilot CLI, Amp, and Claude Code
  via the open Agent Skills standard. Skill Locations cover 8 discovery paths and
  the script probe walks all of them (#30).
- **`validate_skill.py --lens claude|copilot|amp`** — audits a generated SKILL.md
  against each host's rules; `claude` stays the default for CI back-compat (#30).
- **Attribution banner** — `scripts/banner.txt` is printed at the start of each
  run (best-effort, never fails the run).

### Changed
- `SKILL.md` frontmatter trimmed toward the open-standard minimum and the
  description now names all three hosts so each agent's auto-loader picks it up (#30).
- README headline + "Agent Skills" badge; install/usage sections cover all three
  hosts. `docs/ARCHITECTURE.md` shows per-host destination paths (#30).

### Notes
- `allowed-tools` was dropped from the frontmatter for host-neutrality; the skill
  is conformant on all three hosts (validated with all three lenses). If Claude
  users hit permission-prompt friction, the Bash grant from #18 will be restored
  with Claude-native tokens (Copilot ignores the key either way).

## [1.0.0] — 2026-06-08

First formally tagged release. The converter is stable, multi-format, and
validated on real books.

### Added
- **Multi-format extraction** — PDF, EPUB, DOCX, HTML, Markdown, reStructuredText,
  AsciiDoc, RTF, and MOBI/AZW/AZW3 (via Calibre), through a modular `extractor`
  package with per-format parsers and graceful stdlib fallbacks.
- **`extract.py --check`** — preflight that reports which extractors are installed
  for every format and the exact command to install whatever is missing (#21).
- **Adaptive per-chapter depth** — token budget scales with `BOOK_TYPE × DEPTH`;
  study-depth chapters require a worked example, and the cheatsheet is generated as
  a decision/reasoning layer (decision rules, trees, trade-offs, thresholds, tells)
  rather than a keyword list (#20).
- **`tools/discovery_tax.py`** — measures the "Discovery Loop Tax": tokens a
  context-dump vs a discovery loop vs book-to-skill put into context to answer one
  question, on a real book (#23).
- **Update / fold-in workflow** — merge new sources into an existing skill, keeping
  chapter index, topic index, glossary, patterns, and cheatsheet in sync.
- **GitHub Actions CI** — lint (ruff), test matrix (py3.10–3.13), dependency-free
  smoke test, and SKILL.md Claude-conformance validation (#15, #18).

### Changed
- **README positioning** — copyright & fair-use section, "Beyond books" use cases,
  context-dump / RAG / 1M-window FAQ, and a measured Discovery Loop Tax + real
  per-conversion cost table across four books (#19, #27).
- Default output target is `~/.claude/skills/` for Claude Code, with Amp skill
  directories also supported (#13, #14).

### Fixed
- **Chapter detection** — scans the full text (was capped at 50k chars) and counts
  distinct explicit `Chapter N` / `Capítulo N` headings, rejecting numbered list
  items, inline cross-references, and years; adds Portuguese support (#26).
- **Roman-numeral headings** — `I: Loomings`, `II. The Carpet-Bag` are now detected
  with canonical-numeral validation (#28).
- **EPUB extraction** — resolve OPF-relative hrefs in the stdlib zipfile fallback (#11, #12).
- **Batch resilience** — one bad source is skipped with a warning instead of aborting
  the whole run; explicit input order is preserved (#7).

### Known limitations
- Chapter auto-detection needs explicit `Chapter N` / `Capítulo N` or Roman-numeral
  headings. Books that head chapter bodies with bare titles (e.g. *Moby-Dick*, where
  numerals appear only in the table of contents) or use section titles (e.g. Pro Git)
  do not auto-segment.
- Technical PDFs extracted in text mode may lose heading structure; use technical
  mode (Docling) to preserve tables, code, and headings.

[1.2.0]: https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.2.0
[1.1.0]: https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.1.0
[1.0.0]: https://github.com/virgiliojr94/book-to-skill/releases/tag/v1.0.0
