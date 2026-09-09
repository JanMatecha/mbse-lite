# Codex Instructions — Repository Root

## Repository zones

This repository has two intentionally separated scopes:

- `application/` — software development of MBSE Lite.
- `projects/` — engineering/project data using MBSE Lite.

Always determine which scope the requested change belongs to before editing files.

## Scope rules

1. Changes under `application/` must follow `application/AGENTS.md`.
2. Changes under `projects/<name>/` must follow that project's `AGENTS.md`.
3. Project-specific instructions override general repository instructions inside that project.
4. Do not modify project engineering data merely to make an application feature look successful. Use tests or `projects/demo_project` as the regression fixture.
5. Do not modify application behavior merely to encode a one-off project fact. Generalize only when a real reusable need exists.
6. Never copy facts, requirements, decisions, risks, names, files or assumptions from one project into another unless explicitly instructed.
7. Generated outputs are not authoritative project data unless a project explicitly states otherwise.

## Separation of concerns

When working on a technical project and a missing capability is discovered:

- record the engineering need in the project,
- treat the application enhancement as a separate software change,
- add or update application tests,
- then use the new capability on the project.

Do not mix unrelated application refactoring and engineering-model changes in one conceptual task unless necessary.

## General safety

- Preserve stable model IDs once assigned.
- Do not invent technical facts or requirements silently.
- Keep private-project content isolated.
- Prefer small, reviewable changes.
