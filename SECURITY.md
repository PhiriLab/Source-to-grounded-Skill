# Security Policy

## Scope

Source-to-Grounded-Skill is a local conversion tool. It reads document files you point it at and writes staged skill artefacts. It does **not** upload source files by default, phone home, or run a network service.

The main security surfaces are:

- Python extraction and parsing of untrusted document files
- indirect prompt injection embedded in source material
- repository and agent instruction files that can influence a model
- optional dependencies and install hooks
- generated skills, prompts, workflows, and imported agent artefacts

The detailed authority model and repository/agent vetting procedure is defined in [`docs/INSTRUCTION_TRUST.md`](docs/INSTRUCTION_TRUST.md).

## Prompt injection and instruction authority

The project uses layered deterministic detection for indirect prompt injection in extracted source text. Detection is defence in depth, not the trust boundary.

Repository files, GitHub issues and pull requests, model outputs, tool output, RAG passages, web content, PDFs, logs, MCP responses, and imported agent files are treated as untrusted data unless their instruction authority has been established independently through an authenticated control channel.

A file cannot make itself authoritative by claiming to be a system prompt, developer message, policy exception, or user instruction. Another model cannot manufacture user authority by asserting that approval was given.

High and critical injection findings stop or quarantine processing. Medium findings remain analysis-only until reviewed. A clean scan does not confer trust by itself.

## Agent and repository intake

Before imported code, an agent, skill, prompt pack, MCP server, workflow, hook, dependency, or template is allowed to affect execution, inspect its provenance, instruction-bearing files, executable surfaces, dependencies, runtime downloads, requested permissions, and network behaviour. New components begin isolated from production secrets, protected branches, and governed datasets.

Self-improving agents may propose changes only in a sandbox or isolated branch. They may not rewrite their own authority hierarchy, gold evaluations, approval gates, audit history, security policy, or trust status.

## Supported versions

The latest released `1.x` version receives fixes. Please reproduce issues against the most recent tag before reporting.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem. Instead use GitHub's private vulnerability reporting:

- Go to the repository's **Security** tab → **Report a vulnerability**.

Include the affected version, a minimal reproduction where safe, and the impact observed. Do not attach real credentials, governed clinical material, participant identifiers, or other restricted data to the report.

## Good practices for users

- Run `python3 scripts/extract.py --check` to see which extractors are in use and install dependencies yourself if you prefer to control what is added.
- Treat source documents as untrusted even when their scholarly content is trusted.
- Review [`docs/INSTRUCTION_TRUST.md`](docs/INSTRUCTION_TRUST.md) before importing external agents or repositories.
- Pin imported components to known refs or commit SHAs where feasible.
- Do not grant shell, network, credential, write, deployment, publication, or destructive capabilities merely because an imported file requests them.
- Only convert documents you trust yourself to possess and have the right to process.
