# Privacy model

Every source carries a privacy classification, recorded in its provenance
metadata and enforced at the points the pipeline controls.

## Classifications

| Class | Intended material | Enforcement |
|---|---|---|
| `public` | public-domain / openly licensed | none beyond defaults |
| `copyrighted-private` (default) | books and papers you own for personal reference | staging is private (0700/0600); evidence spans bounded |
| `institutional-confidential` | protocols, internal policy, unpublished work | as above; treat staging as confidential storage |
| `clinical-restricted` | anything potentially participant-identifiable | all of the above, plus identifier scanning on generated output (critical findings, publication-blocking); identifier evidence is never reproduced in findings |

## Mechanics

- Staging directories and files are created `0700`/`0600` (best-effort on
  filesystems that support it).
- The pipeline itself makes **no network calls** in any mode; extraction
  and scanning are local. `--no-network` is accepted for compatibility and
  as a statement of intent.
- Quarantined sources are copies under `.book-to-skill/quarantine/`, same
  permissions.
- Working data lives under the project's `.book-to-skill/`; deleting that
  directory removes every intermediate. Nothing is written to shared temp
  locations by the grounded pipeline (the legacy extraction path keeps
  upstream's `$BOOK_SKILL_WORKDIR` behaviour).
- Generated skills must not contain participant-level material; for
  `clinical-restricted` staging, the output scanner blocks emails,
  DOB-adjacent dates, NHS/phone-shaped numbers, and participant-ID
  patterns. See LIMITATIONS.md for why this is a control, not a guarantee.

## What the user must still decide

Where staging lives (an encrypted volume for restricted material), when to
delete it, and whether cloud-hosted generation is acceptable for a given
classification — the pipeline cannot see which model host the agent runs
on, so `clinical-restricted` material should only be converted in
environments already approved for it.
