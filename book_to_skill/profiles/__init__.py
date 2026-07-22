"""Declarative domain profiles.

A profile is a YAML document declaring, for one domain of source material:

    name, description
    defaults:      world_knowledge / privacy / citation_mode / security /
                   require_review
    outputs:       files generation must produce (file, purpose, required)
    preserve:      what the generation must keep (argument, contraindications…)
    constraints:   hard rules, surfaced verbatim in generation instructions
    analytical_dimensions: schema dimensions (not decorative paragraphs)
    capability_profile:    permissions block for the generated skill

Profiles configure the same machinery; they never loosen security or
provenance requirements — loader validation enforces that scholarly/clinical
profiles keep world knowledge off or labelled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

PROFILE_DIR = Path(__file__).resolve().parent

PROFILE_NAMES = (
    "scholarly-book",
    "clinical-method",
    "cbt-manual",
    "global-mental-health",
    "cultural-adaptation",
    "clinical-trial",
    "research-cluster",
    "teaching-and-supervision",
    "policy-and-implementation",
    "invention-and-design",
)

# Profiles whose material makes unlabelled model knowledge unacceptable.
_STRICT_KNOWLEDGE = frozenset(PROFILE_NAMES) - {"invention-and-design"}

_ALLOWED_DEFAULT_KEYS = {
    "world_knowledge", "privacy", "citation_mode", "security", "require_review",
}


class ProfileError(ValueError):
    pass


@dataclass
class OutputSpec:
    file: str
    purpose: str
    required: bool = True


@dataclass
class Profile:
    name: str
    description: str
    defaults: dict = field(default_factory=dict)
    outputs: list[OutputSpec] = field(default_factory=list)
    preserve: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    analytical_dimensions: list[str] = field(default_factory=list)
    capability_profile: dict = field(default_factory=dict)

    @property
    def required_files(self) -> list[str]:
        return [o.file for o in self.outputs if o.required]


def _validate(profile: Profile) -> Profile:
    if profile.name not in PROFILE_NAMES:
        raise ProfileError(f"unknown profile name {profile.name!r}")
    unknown = set(profile.defaults) - _ALLOWED_DEFAULT_KEYS
    if unknown:
        raise ProfileError(f"{profile.name}: unknown default keys {sorted(unknown)}")
    wk = profile.defaults.get("world_knowledge", "off")
    if profile.name in _STRICT_KNOWLEDGE and wk == "unrestricted":
        raise ProfileError(
            f"{profile.name}: world_knowledge may not default to 'unrestricted'"
        )
    caps = profile.capability_profile.get("permissions", {})
    for risky in ("shell", "network", "write_files", "access_secrets"):
        if caps.get(risky):
            raise ProfileError(
                f"{profile.name}: generated skills may not request {risky!r}"
            )
    if not any(o.file == "SKILL.md" for o in profile.outputs):
        raise ProfileError(f"{profile.name}: outputs must include SKILL.md")
    return profile


def load_profile(name: str, directory: Path = PROFILE_DIR) -> Profile:
    if yaml is None:
        raise ProfileError("PyYAML is required for profiles: pip install pyyaml")
    path = Path(directory) / f"{name}.yaml"
    if not path.exists():
        raise ProfileError(
            f"no such profile {name!r}; available: {', '.join(PROFILE_NAMES)}"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    outputs = [OutputSpec(**o) for o in data.get("outputs", [])]
    profile = Profile(
        name=data["name"],
        description=data.get("description", ""),
        defaults=data.get("defaults", {}),
        outputs=outputs,
        preserve=data.get("preserve", []),
        constraints=data.get("constraints", []),
        analytical_dimensions=data.get("analytical_dimensions", []),
        capability_profile=data.get("capability_profile", {}),
    )
    return _validate(profile)


def list_profiles() -> list[str]:
    return list(PROFILE_NAMES)
