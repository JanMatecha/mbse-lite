# Codex Instructions — Garden Tool Shed

## Scope

These instructions apply to `projects/garden_tool_shed/`.

This project has two intentionally separated working areas:

- `mbse/` — system engineering and technical model,
- `project_management/` — planning and tracking of work.

Use the nested `AGENTS.md` in each area for detailed rules.

## Project objective

Support the structured development of a garden tool shed from needs and requirements through concept selection, architecture, verification and eventual construction readiness.

## Separation rule

Before editing, classify the requested change:

- If it changes what the shed shall do, why, its architecture, concepts, technical decisions, verification, engineering assumptions/issues/risks or engineering data, edit `mbse/`.
- If it changes work packages, owners, estimates, deadlines, progress or milestones, edit `project_management/`.
- If project work is connected to engineering, preserve that connection through an explicit relation rather than duplicating engineering content in project-management files.

## General rules

- Markdown files are the project source of truth.
- Preserve assigned IDs; never silently renumber them.
- Do not invent technical facts, dimensions, materials, loads, regulations, costs or dates.
- Record unknown technical information as `TBD` or an engineering `ISSUE-*`.
- Keep cross-area traceability explicit.
- Validate the whole project with MBSE Lite after coherent changes when available.
