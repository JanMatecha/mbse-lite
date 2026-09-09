# Codex Instructions — Garden Tool Shed

## Scope

These instructions apply only to `projects/garden_tool_shed/`.

This directory contains engineering project data, not MBSE-lite application source code. Do not modify `application/` unless the user explicitly asks to develop the framework.

## Project objective

Support the structured development of a garden tool shed from needs and requirements through concept selection, architecture, verification planning and project execution.

## Engineering rules

- Markdown files in this directory are the project source of truth.
- Preserve assigned IDs; never silently renumber them.
- Do not invent technical facts, dimensions, materials, loads, regulations, costs or dates.
- Record unknown but necessary information as `TBD` or create an `ISSUE-*` object.
- Separate needs from requirements and requirements from proposed solutions.
- Record important choices as `DEC-*` with rationale.
- Keep explicit relations in `07_relations.md`.
- Prefer concise engineering statements that can later be verified.
- When adding a requirement, consider how it will be verified.
- When proposing concepts, distinguish alternatives from selected architecture.
- Project-management items may reference engineering objects through relations.

## Initial workflow

1. Clarify stakeholder/user needs.
2. Capture site and usage constraints.
3. Derive measurable requirements.
4. Define functions.
5. Generate and compare concepts.
6. Select architecture and record decisions.
7. Define verification and construction readiness.
8. Track tasks, issues, risks and milestones.

## Codex behavior

When asked to update the project:

1. inspect existing project files first,
2. make the smallest coherent change,
3. maintain traceability,
4. flag missing information rather than guessing,
5. validate the project with MBSE-lite when available.
