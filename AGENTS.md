# Codex development guidance

## Purpose

This repository develops YouTube Stream Analyzer, a tool that collects and stores data from YouTube streams and supports discovery and evaluation of clip candidates.

## Canonical documents

Read these before making implementation decisions:

1. `docs/product-roadmap.md` — product direction and phased target state
2. `docs/architecture.md` — system responsibilities and technology choices
3. `docs/development-milestones.md` — canonical milestone definitions and completion criteria
4. `docs/implementation-plans/` — milestone-specific implementation plans
5. `docs/decisions/` — architecture decision records

When documents conflict, prefer the most specific canonical document. `docs/development-milestones.md` is authoritative for milestone scope and completion.

## Development principles

- Deliver each milestone as an end-to-end, independently usable increment.
- Start from the user operation scenario and work vertically through UI, API, persistence, and processing.
- Do not expose unfinished future features in the normal UI.
- Do not introduce speculative abstractions for later milestones.
- Do not freeze unresolved product or architecture questions through implementation.
- Record material architecture decisions as ADRs when the decision becomes necessary.
- Use real YouTube stream data for milestone completion demonstrations unless an external constraint prevents it.
- Keep diagnostics and developer information out of the primary user experience.

## Planning workflow

Before implementing a milestone:

1. Create an implementation plan from `docs/implementation-plans/template.md`.
2. Confirm the user scenario, scope, excluded work, and unresolved decisions.
3. Split work into dependency-ordered issues.
4. Implement and validate one coherent vertical slice at a time.
5. Record the completion demonstration procedure.

## Validation

Run the repository-wide validation command before publishing changes:

```bash
make check
```

Add milestone-specific checks to this command as applications and services are introduced.

## Git and pull requests

- Use a dedicated branch for each issue or coherent change.
- Keep commits focused and explain the intent rather than the editing process.
- Include validation results and remaining limitations in the pull request description.
- Do not combine unrelated cleanup with milestone work.

## Agent Skills

Codex Agent Skills are maintained separately by the repository owner. The repository only reserves `.agents/skills/` as their repository-level placement directory. Do not add or modify Skill contents unless explicitly requested.
