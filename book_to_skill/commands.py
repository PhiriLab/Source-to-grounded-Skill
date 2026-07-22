"""Subcommand CLI for the grounded scholarly compiler.

Deterministic pipeline stages live here; the analytical work (claim
extraction, synthesis) is done by the host agent following SKILL.md against
a staging area this CLI prepares and later validates.

Backward compatibility: invocations whose first argument is not a known
subcommand fall through to the upstream extraction behaviour, so
`source-to-skill <paths>` still runs plain extraction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from book_to_skill import utils
from book_to_skill.profiles import PROFILE_NAMES, load_profile
from book_to_skill.provenance.citations import citation_coverage, validate_markers
from book_to_skill.provenance.ids import sha256_file, source_id_for
from book_to_skill.provenance.ledger import ClaimsLedger
from book_to_skill.provenance.models import GenerationManifest, PRIVACY_CLASSES, Source
from book_to_skill.provenance.trace import trace_claim
from book_to_skill.review.decisions import DecisionStore
from book_to_skill.review.packet import build_review_packet
from book_to_skill.review.state import SkillState, publication_gate, utc_now
from book_to_skill.security import (
    evaluate_findings,
    sanitize_text,
    scan_for_injection,
    scan_generated_dir,
)
from book_to_skill.security.findings import FindingsReport, Severity
from book_to_skill.security.policy import GateDecision, SecurityPolicy
from book_to_skill.staging import StagingArea, write_private
from book_to_skill.structure import detect_sections, sections_from_map

GENERATOR_VERSION = "2.0.0-grounded"

# Below this word count a source is almost certainly a failed extraction
# (typically a scanned/image PDF with no text layer), not a real document.
MIN_EXTRACTED_WORDS = 30

SUBCOMMANDS = (
    "inspect", "scan", "convert", "validate", "trace", "diff",
    "review", "approve", "reject", "annotate", "mark-reviewed",
    "publish", "evaluate", "profiles",
)


def _err(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)


def _load_staging(path: str) -> Path:
    staged = Path(path).resolve()
    if not (staged / "provenance").is_dir():
        raise SystemExit(f"ERROR: {staged} is not a staged skill (no provenance/ dir)")
    return staged


def _manifest_path(staged: Path) -> Path:
    return staged / "provenance" / "manifest.json"


def _load_manifest(staged: Path) -> GenerationManifest:
    return GenerationManifest.from_dict(
        json.loads(_manifest_path(staged).read_text(encoding="utf-8"))
    )


def _save_manifest(staged: Path, manifest: GenerationManifest) -> None:
    write_private(_manifest_path(staged), json.dumps(manifest.to_dict(), indent=2))


def _extract_sources(paths: list[str], mode: str, install: str):
    files = utils.resolve_input_files(paths)
    if not files:
        raise SystemExit(f"ERROR: no supported files found in: {', '.join(paths)}")
    results, errors = [], []
    for f in files:
        try:
            results.append((f, utils.extract_single_file(f, mode, install)))
        except utils.ExtractionError as exc:
            errors.append(f"{f.name}: {exc}")
    if not results:
        raise SystemExit("ERROR: all sources failed extraction:\n  " + "\n  ".join(errors))
    return results, errors


# --- inspect / scan ----------------------------------------------------------

def cmd_inspect(args) -> int:
    results, errors = _extract_sources(args.sources, args.mode, "no")
    for path, res in results:
        print(f"\n{res['filename']}  ({res['format']}, {res['extraction_method']})")
        print(f"  sha256   : {sha256_file(path)}")
        print(f"  size     : {res['file_size_mb']} MB, ~{res['estimated_tokens']:,} tokens")
        print(f"  chapters : {res['chapters_detected']} detected, ToC: {'yes' if res['has_toc'] else 'no'}")
    for e in errors:
        print(f"  WARNING: {e}", file=sys.stderr)
    return 0


def cmd_scan(args) -> int:
    results, _ = _extract_sources(args.sources, args.mode, "no")
    policy = SecurityPolicy(args.security)
    total = FindingsReport()
    for path, res in results:
        sid = source_id_for(sha256_file(path))
        san = sanitize_text(res["text"], source_id=sid)
        total.extend(san.findings)
        total.extend(scan_for_injection(san.sanitized_text, source_id=sid))
    decision = evaluate_findings(total, policy)
    for f in total.findings:
        print(f"[{f.risk.value:8s}] {f.category:28s} {f.source_id} {f.location}: {f.evidence[:80]}")
    print(f"\n{len(total.findings)} finding(s); gate decision ({policy.mode}): {decision.value}")
    return 0 if decision in (GateDecision.PROCEED, GateDecision.ANALYSIS_ONLY) else 1


# --- convert (prepare staging) -----------------------------------------------

def cmd_convert(args) -> int:
    profile = load_profile(args.profile)
    d = profile.defaults
    privacy = args.privacy or d.get("privacy", "copyrighted-private")
    world = args.world_knowledge or d.get("world_knowledge", "off")
    security_mode = args.security or d.get("security", "standard")
    policy = SecurityPolicy(security_mode)
    check_ids = privacy == "clinical-restricted" or args.redact_identifiers

    area = StagingArea(args.output, args.skill_id).create()
    results, extraction_errors = _extract_sources(args.sources, args.mode, args.install_missing)

    # Empty-extraction guard: a source that yields almost no words is almost
    # always a scanned/image PDF with no text layer (surfaced by the first
    # real-world trial). Fail loudly with an OCR hint rather than silently
    # staging an empty run.
    thin = [(p, r) for p, r in results if r.get("words", 0) < MIN_EXTRACTED_WORDS]
    if thin and not args.allow_thin_source:
        names = ", ".join(f"{p.name} ({r.get('words', 0)} words)" for p, r in thin)
        _err(f"near-empty extraction: {names}")
        _err("This usually means a scanned/image PDF with no text layer — there "
             "is nothing to ground claims against. OCR it first (e.g. "
             "`ocrmypdf input.pdf output.pdf`) and convert the OCR'd file, or "
             "pass --allow-thin-source to override.")
        return 2

    sources: list[Source] = []
    all_findings = FindingsReport()
    sanitization_logs = []
    sections = []
    structure_warnings = list(extraction_errors)
    map_text = Path(args.structure_map).read_text(encoding="utf-8") if args.structure_map else None

    for n, (path, res) in enumerate(results, start=1):
        digest = sha256_file(path)
        sid = source_id_for(digest)
        key = f"BOOK{n}"
        src = Source(
            source_id=sid, title=res["filename"], path=str(path), sha256=digest,
            privacy=privacy, extraction_tool=res["extraction_method"],
            extraction_tool_version=GENERATOR_VERSION, extraction_timestamp=utc_now(),
            citation_key=key,
        )
        sources.append(src)

        san = sanitize_text(res["text"], source_id=sid)
        all_findings.extend(san.findings)
        all_findings.extend(scan_for_injection(san.sanitized_text, source_id=sid))
        sanitization_logs.append(san.log_dict(sid))

        # Original extraction preserved verbatim; sanitised copy is what the
        # agent analyses. Both are private files.
        write_private(area.provenance_dir / "sources" / f"{sid}.txt", res["text"])
        write_private(area.provenance_dir / "sources_sanitized" / f"{sid}.txt",
                      san.sanitized_text)

        if map_text is not None:
            sres = sections_from_map(map_text, res["text"], sid, key)
        else:
            sres = detect_sections(res["text"], sid, key)
        sections.extend(s.to_dict() for s in sres.sections)
        structure_warnings.extend(sres.warnings)

    decision = evaluate_findings(all_findings, policy)
    all_findings.write_jsonl(area.security_dir / "source_findings.jsonl")
    write_private(area.security_dir / "sanitization_log.json",
                  json.dumps(sanitization_logs, indent=2, ensure_ascii=False))
    write_private(area.provenance_dir / "sources.json",
                  json.dumps([s.to_dict() for s in sources], indent=2, ensure_ascii=False))
    write_private(area.provenance_dir / "sections.json",
                  json.dumps(sections, indent=2, ensure_ascii=False))
    if structure_warnings:
        write_private(area.provenance_dir / "structure_warnings.json",
                      json.dumps(structure_warnings, indent=2, ensure_ascii=False))
    if map_text is not None:
        write_private(area.provenance_dir / "structure-map.yaml", map_text)

    if decision == GateDecision.QUARANTINE:
        for src in sources:
            area.quarantine_source(Path(src.path), src.sha256)
        _err("critical security findings — sources quarantined, generation blocked.")
        _err(f"findings: {area.security_dir / 'source_findings.jsonl'}")
        return 2
    if decision == GateDecision.STOP:
        _err(f"high-risk security findings under --security {security_mode} — generation blocked.")
        _err(f"findings: {area.security_dir / 'source_findings.jsonl'}")
        return 2

    manifest = GenerationManifest(
        skill_id=args.skill_id, state="draft", profile=profile.name,
        privacy=privacy, world_knowledge=world, citation_mode=args.citation_mode,
        security_mode=security_mode, generator_version=GENERATOR_VERSION,
        created_at=utc_now(), sources=[s.to_dict() for s in sources],
        state_history=[{"state": "draft", "at": utc_now(),
                        "gate_decision": decision.value}],
    )
    _save_manifest(area.skill_dir, manifest)

    mode_note = ("ANALYSIS-ONLY (medium findings present — publication blocked "
                 "until findings are reviewed)" if decision == GateDecision.ANALYSIS_ONLY
                 else "full generation permitted")
    print(f"Staged: {area.skill_dir}")
    print(f"  profile        : {profile.name}")
    print(f"  privacy        : {privacy}   world-knowledge: {world}")
    print(f"  security       : {security_mode} -> {decision.value} ({mode_note})")
    print(f"  sources        : {len(sources)}   sections: {len(sections)}")
    if structure_warnings:
        print(f"  warnings       : {len(structure_warnings)} (provenance/structure_warnings.json)")
    print(f"  identifiers    : {'scanned on output' if check_ids else 'not scanned (privacy class)'}")
    print("\nNext: the host agent generates the skill files INTO THIS STAGING "
          "DIRECTORY per SKILL.md,\nthen run: source-to-skill validate "
          f"{area.skill_dir}")
    return 0


# --- validate ----------------------------------------------------------------

def _gather_validation(staged: Path):
    manifest = _load_manifest(staged)
    ledger = ClaimsLedger.load(staged / "provenance" / "claims.jsonl")
    source_texts = {}
    src_dir = staged / "provenance" / "sources"
    for f in src_dir.glob("*.txt"):
        source_texts[f.stem] = f.read_text(encoding="utf-8")
    ledger_problems = ledger.validate(source_texts or None)

    known_sources = {s["citation_key"] for s in manifest.sources}
    known_claims = {c.claim_id for c in ledger}
    sections_file = staged / "provenance" / "sections.json"
    known_sections = None
    if sections_file.exists():
        by_key = {s["source_id"]: s for s in manifest.sources}
        known_sections = set()
        for sec in json.loads(sections_file.read_text(encoding="utf-8")):
            src = by_key.get(sec["source_id"])
            if src:
                known_sections.add(f"{src['citation_key']}:{sec['citation_label']}")

    citation_problems, uncited = [], []
    for md in sorted(staged.rglob("*.md")):
        rel = md.relative_to(staged)
        if str(rel).startswith(("review/", "security/")):
            continue
        text = md.read_text(encoding="utf-8")
        citation_problems += [f"{rel}: {p}" for p in validate_markers(
            text, known_sources, known_sections, known_claims)]
        _, un = citation_coverage(text)
        uncited += [f"{rel}: {u[:120]}" for u in un]

    check_ids = manifest.privacy == "clinical-restricted"
    output_findings = scan_generated_dir(staged, check_identifiers=check_ids)
    # Pipeline internals legitimately contain the very patterns we scan for
    # (findings files and REVIEW.md quote evidence; preserved sources ARE the
    # untrusted input). Only generated artifacts count as output.
    internal = tuple(
        str(p.resolve().as_posix()) + "/"
        for p in (staged / "security", staged / "review",
                  staged / "provenance" / "sources",
                  staged / "provenance" / "sources_sanitized")
    )
    output_findings.findings = [
        f for f in output_findings.findings
        if not str(Path(f.source_id).resolve().as_posix()).startswith(internal)
    ]
    source_findings = FindingsReport.read_jsonl(staged / "security" / "source_findings.jsonl")
    return manifest, ledger, ledger_problems, citation_problems, uncited, source_findings, output_findings


def cmd_validate(args) -> int:
    staged = _load_staging(args.skill_dir)
    (manifest, ledger, ledger_problems, citation_problems, uncited,
     source_findings, output_findings) = _gather_validation(staged)

    output_findings.write_jsonl(staged / "security" / "output_findings.jsonl")
    profile = load_profile(manifest.profile)
    missing = [f for f in profile.required_files
               if not (staged / f).exists()]

    packet = build_review_packet(
        ledger, source_findings, output_findings, ledger_problems,
        citation_problems, uncited,
        extraction_warnings=(
            json.loads((staged / "provenance" / "structure_warnings.json").read_text(encoding="utf-8"))
            if (staged / "provenance" / "structure_warnings.json").exists() else []
        ) + [f"missing required output: {m}" for m in missing],
    )
    write_private(staged / "review" / "REVIEW.md", packet)

    clean_security = not output_findings.at_or_above(Severity.MEDIUM)
    clean_sources = not ledger_problems and not citation_problems and not missing
    state = SkillState(manifest.state)
    if state == SkillState.DRAFT and clean_security:
        manifest.state = SkillState.SECURITY_CLEARED.value
        manifest.state_history.append({"state": manifest.state, "at": utc_now()})
        state = SkillState.SECURITY_CLEARED
    if state == SkillState.SECURITY_CLEARED and clean_sources and len(ledger):
        manifest.state = SkillState.SOURCE_VERIFIED.value
        manifest.state_history.append({"state": manifest.state, "at": utc_now()})
    _save_manifest(staged, manifest)

    cov_all = []
    for md in sorted(staged.rglob("*.md")):
        if not str(md.relative_to(staged)).startswith(("review/", "security/")):
            cov, _ = citation_coverage(md.read_text(encoding="utf-8"))
            cov_all.append(cov)
    coverage = sum(cov_all) / len(cov_all) if cov_all else 0.0

    print(f"State           : {manifest.state}")
    print(f"Claims          : {len(ledger)}")
    print(f"Citation coverage: {coverage:.2%}  (uncited paragraphs: {len(uncited)})")
    print(f"Ledger problems : {len(ledger_problems)}")
    print(f"Citation problems: {len(citation_problems)}")
    print(f"Missing outputs : {len(missing)}")
    print(f"Output findings : {len(output_findings.findings)}")
    print(f"Review packet   : {staged / 'review' / 'REVIEW.md'}")
    ok = clean_security and clean_sources
    return 0 if ok else 1


# --- trace / diff ------------------------------------------------------------

def cmd_trace(args) -> int:
    staged = _load_staging(args.skill_dir)
    source_texts = {}
    for f in (staged / "provenance" / "sources").glob("*.txt"):
        source_texts[f.stem] = f.read_text(encoding="utf-8")
    try:
        result = trace_claim(staged, args.claim_id, source_texts or None)
    except KeyError as exc:
        _err(str(exc))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_diff(args) -> int:
    old = ClaimsLedger.load(Path(args.old) / "provenance" / "claims.jsonl")
    new = ClaimsLedger.load(Path(args.new) / "provenance" / "claims.jsonl")
    old_ids = {c.claim_id for c in old}
    new_ids = {c.claim_id for c in new}
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    changed = sorted(
        cid for cid in old_ids & new_ids
        if old.get(cid).to_dict() != new.get(cid).to_dict()
    )
    for cid in added:
        print(f"+ {cid}: {new.get(cid).paraphrase[:100]}")
    for cid in removed:
        print(f"- {cid}: {old.get(cid).paraphrase[:100]}")
    for cid in changed:
        print(f"~ {cid}: {new.get(cid).paraphrase[:100]}")
    print(f"\n{len(added)} added, {len(removed)} withdrawn, {len(changed)} modified")
    return 0


# --- review / decisions / publish -------------------------------------------

def cmd_review(args) -> int:
    staged = _load_staging(args.skill_dir)
    packet = staged / "review" / "REVIEW.md"
    if not packet.exists():
        _err("no REVIEW.md — run `source-to-skill validate` first")
        return 1
    print(packet.read_text(encoding="utf-8"))
    return 0


def _decision_cmd(args, action: str) -> int:
    staged = _load_staging(args.skill_dir)
    ledger = ClaimsLedger.load(staged / "provenance" / "claims.jsonl")
    claim = ledger.get(args.claim_id)
    if claim is None:
        _err(f"claim {args.claim_id} not found")
        return 1
    store = DecisionStore(staged / "review" / "decisions.jsonl")
    if action == "approve":
        store.approve(claim, reviewer=args.reviewer, reason=args.reason or "")
    elif action == "reject":
        if not args.reason:
            _err("--reason is required to reject a claim")
            return 1
        store.reject(claim, reviewer=args.reviewer, reason=args.reason)
    else:
        if not args.note:
            _err("--note is required to annotate a claim")
            return 1
        store.annotate(claim, reviewer=args.reviewer, annotation=args.note)
    ledger.save()
    print(f"{args.claim_id}: {claim.review_status}")
    return 0


def cmd_mark_reviewed(args) -> int:
    staged = _load_staging(args.skill_dir)
    manifest = _load_manifest(staged)
    if manifest.state != SkillState.SOURCE_VERIFIED.value:
        _err(f"state is {manifest.state!r}; run validate until source-verified first")
        return 1
    ledger = ClaimsLedger.load(staged / "provenance" / "claims.jsonl")
    unreviewed_high_impact = [
        c.claim_id for c in ledger
        if c.review_status == "unreviewed" and (
            c.claim_type == "clinical_recommendation"
            or c.epistemic_status in ("editorial_inference", "cross_source_synthesis",
                                      "contested_claim"))
    ]
    if unreviewed_high_impact and not args.force:
        _err("unreviewed high-impact claims remain: " + ", ".join(unreviewed_high_impact[:10]))
        _err("approve/reject them, or pass --force to record review anyway")
        return 1
    manifest.state = SkillState.EXPERT_REVIEWED.value
    manifest.reviewed_by = args.reviewer
    manifest.reviewed_at = utc_now()
    manifest.state_history.append({"state": manifest.state, "at": utc_now(),
                                   "reviewer": args.reviewer})
    _save_manifest(staged, manifest)
    print(f"State: {manifest.state} (reviewer: {args.reviewer})")
    return 0


def cmd_publish(args) -> int:
    staged = _load_staging(args.skill_dir)
    (manifest, ledger, ledger_problems, citation_problems, _uncited,
     _source_findings, output_findings) = _gather_validation(staged)

    gate = publication_gate(
        SkillState(manifest.state), output_findings, ledger_problems,
        citation_problems, reviewed_medium_findings=args.findings_reviewed,
        require_expert_review=not args.no_require_review,
    )
    if not gate:
        _err("publication blocked:")
        for r in gate.reasons:
            _err(f"  - {r}")
        return 1

    area = StagingArea(staged.parent.parent.parent, manifest.skill_id)
    dest = area.publish_to(Path(args.to))
    manifest.state = SkillState.PUBLISHED.value
    manifest.state_history.append({"state": manifest.state, "at": utc_now(),
                                   "published_to": str(dest)})
    _save_manifest(staged, manifest)
    _save_manifest(dest, manifest)
    print(f"Published: {dest}")
    return 0


def cmd_evaluate(args) -> int:
    try:
        from evaluation.metrics import evaluate
    except ImportError:
        _err("the evaluation harness ships with the repository checkout, not "
             "the installed package — run from the repo root")
        return 1
    staged = _load_staging(args.skill_dir)
    gold = None
    if args.gold_contraindications:
        gold = [line.strip() for line in
                Path(args.gold_contraindications).read_text(encoding="utf-8").splitlines()
                if line.strip()]
    report = evaluate(staged, gold)
    md = report.to_markdown()
    write_private(staged / "review" / "EVALUATION.md", md)
    print(md)
    return 0 if report.passed else 1


def cmd_profiles(_args) -> int:
    for name in PROFILE_NAMES:
        p = load_profile(name)
        print(f"{name:26s} {p.description.strip().splitlines()[0]}")
    return 0


# --- parser ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="source-to-skill",
        description="Grounded scholarly knowledge compiler (fork of book-to-skill).",
    )
    sub = parser.add_subparsers(dest="command")

    def add_mode(p):
        p.add_argument("--mode", choices=("technical", "text"), default="text")

    p = sub.add_parser("inspect", help="extract and report source metadata")
    p.add_argument("sources", nargs="+")
    add_mode(p)
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("scan", help="security-scan sources without staging")
    p.add_argument("sources", nargs="+")
    add_mode(p)
    p.add_argument("--security", choices=("strict", "standard", "permissive"),
                   default="standard")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("convert", help="extract, scan, and stage sources for generation")
    p.add_argument("sources", nargs="+")
    p.add_argument("--skill-id", required=True)
    p.add_argument("--profile", choices=PROFILE_NAMES, default="scholarly-book")
    p.add_argument("--privacy", choices=PRIVACY_CLASSES, default=None)
    p.add_argument("--world-knowledge", choices=("off", "labelled", "unrestricted"),
                   default=None)
    p.add_argument("--citation-mode", choices=("claim", "section"), default="claim")
    p.add_argument("--security", choices=("strict", "standard", "permissive"),
                   default=None)
    p.add_argument("--output", default=".", help="project root for .source-to-skill/staging")
    p.add_argument("--structure-map", default=None)
    p.add_argument("--redact-identifiers", action="store_true")
    p.add_argument("--no-network", action="store_true",
                   help="accepted for compatibility; the pipeline never uses the network")
    p.add_argument("--local-extraction-only", action="store_true",
                   help="alias of --install-missing no")
    p.add_argument("--install-missing", choices=("ask", "yes", "no"), default="no")
    p.add_argument("--allow-thin-source", action="store_true",
                   help="proceed even if a source extracts almost no text "
                        "(bypasses the scanned-PDF/OCR guard)")
    add_mode(p)
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("validate", help="validate a staged skill; write REVIEW.md")
    p.add_argument("skill_dir")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("trace", help="trace a claim to its source passage")
    p.add_argument("claim_id")
    p.add_argument("--skill", dest="skill_dir", required=True)
    p.set_defaults(func=cmd_trace)

    p = sub.add_parser("diff", help="diff two staged skills' claims ledgers")
    p.add_argument("old")
    p.add_argument("new")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("review", help="print the review packet")
    p.add_argument("skill_dir")
    p.set_defaults(func=cmd_review)

    for action in ("approve", "reject", "annotate"):
        p = sub.add_parser(action, help=f"{action} a claim")
        p.add_argument("claim_id")
        p.add_argument("--skill", dest="skill_dir", required=True)
        p.add_argument("--reviewer", required=True)
        p.add_argument("--reason", default=None)
        p.add_argument("--note", default=None)
        p.set_defaults(func=lambda a, _act=action: _decision_cmd(a, _act))

    p = sub.add_parser("mark-reviewed", help="record expert review of a staged skill")
    p.add_argument("skill_dir")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_mark_reviewed)

    p = sub.add_parser("publish", help="publish a staged skill to a skills root")
    p.add_argument("skill_dir")
    p.add_argument("--to", required=True, help="destination skills root")
    p.add_argument("--findings-reviewed", action="store_true",
                   help="attest that medium security findings were reviewed")
    p.add_argument("--no-require-review", action="store_true",
                   help="allow publish from source-verified (recorded in history)")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("evaluate", help="run release-gating metrics on a staged skill")
    p.add_argument("skill_dir")
    p.add_argument("--gold-contraindications", default=None,
                   help="file with one gold contraindication per line")
    p.set_defaults(func=cmd_evaluate)

    p = sub.add_parser("profiles", help="list domain profiles")
    p.set_defaults(func=cmd_profiles)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in SUBCOMMANDS or (argv and argv[0] in ("-h", "--help")):
        args = build_parser().parse_args(argv)
        if not getattr(args, "func", None):
            build_parser().print_help()
            return 1
        if getattr(args, "local_extraction_only", False):
            args.install_missing = "no"
        return args.func(args)
    # Legacy upstream behaviour: plain extraction.
    utils.main()
    return 0
