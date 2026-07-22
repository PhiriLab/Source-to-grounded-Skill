"""Staged output layout: generation never writes into a live skills root.

Layout under <project>/.source-to-skill/:

    staging/<skill-id>/
        SKILL.md, chapters/, ...      # generated artifacts (draft)
        provenance/
            claims.jsonl              # claims ledger
            sources.json              # source manifest (hashes, editions, ...)
            manifest.json             # generation manifest + skill state
        security/
            source_findings.jsonl
            output_findings.jsonl
            sanitization_log.json
        review/
            REVIEW.md
            decisions.jsonl
    quarantine/<source-hash>/         # quarantined source copies + findings

Directories are created 0700 and files written 0600 so restricted material
never lands world-readable (docs/THREAT_MODEL.md, T4).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

STAGING_ROOT_NAME = ".source-to-skill"

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def validate_slug(slug: str) -> str:
    """Reject path-traversal and hostile skill ids before they touch the fs."""
    if not _SLUG.match(slug):
        raise ValueError(
            f"invalid skill id {slug!r}: lowercase letters, digits and hyphens only"
        )
    return slug


def _mkdir_private(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass  # e.g. permission-less filesystems; best effort
    return path


def write_private(path: Path, content: str) -> None:
    _mkdir_private(path.parent)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class StagingArea:
    def __init__(self, project_root: Path | str = ".", skill_id: str = "skill"):
        self.skill_id = validate_slug(skill_id)
        self.root = Path(project_root).resolve() / STAGING_ROOT_NAME
        self.skill_dir = self.root / "staging" / self.skill_id
        self.provenance_dir = self.skill_dir / "provenance"
        self.security_dir = self.skill_dir / "security"
        self.review_dir = self.skill_dir / "review"
        self.quarantine_root = self.root / "quarantine"

    def create(self) -> "StagingArea":
        for d in (self.skill_dir, self.provenance_dir, self.security_dir, self.review_dir):
            _mkdir_private(d)
        return self

    # -- path safety ---------------------------------------------------------

    def resolve_inside(self, relative: str) -> Path:
        """Resolve a path strictly inside the staged skill dir.

        Refuses absolute paths, `..` escapes, and symlink escapes.
        """
        candidate = (self.skill_dir / relative)
        resolved = candidate.resolve()
        skill_root = self.skill_dir.resolve()
        if not str(resolved).startswith(str(skill_root) + os.sep) and resolved != skill_root:
            raise ValueError(f"path escapes staging area: {relative!r}")
        return resolved

    # -- quarantine ----------------------------------------------------------

    def quarantine_source(self, source_path: Path, source_hash: str) -> Path:
        dest_dir = _mkdir_private(self.quarantine_root / source_hash[:16])
        dest = dest_dir / Path(source_path).name
        shutil.copy2(source_path, dest)
        try:
            os.chmod(dest, 0o600)
        except OSError:
            pass
        return dest

    # -- publish -------------------------------------------------------------

    def publish_to(self, skills_root: Path) -> Path:
        """Copy the staged artifacts (not the provenance/security/review
        internals' working copies — those travel too, for traceability) into
        a live skills root. Caller is responsible for having passed the
        publication gate first (see book_to_skill.review.state).
        """
        dest = Path(skills_root).resolve() / self.skill_id
        if dest.exists():
            raise FileExistsError(
                f"{dest} already exists — remove it or choose another skill id"
            )
        shutil.copytree(self.skill_dir, dest, symlinks=False)
        return dest
