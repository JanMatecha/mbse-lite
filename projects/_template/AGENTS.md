# Codex Instructions — Project Root

## Scope

These instructions apply to this project root only, regardless of where the directory is stored.

The project is intentionally divided into:

- `mbse/` — system engineering and technical model,
- `project_management/` — planning and tracking of work.

Use the nested `AGENTS.md` files for area-specific rules.

## General rules

- Markdown model content is authoritative unless this project explicitly states otherwise.
- Preserve stable IDs.
- Do not invent technical facts, measurements, constraints, requirements or decisions.
- Label assumptions and proposals clearly.
- Keep MBSE content and project-management content in their respective areas.
- Connect work to engineering through explicit relations instead of duplicating information.
- Treat this directory as the writable project boundary unless the project explicitly authorizes another controlled target.
- Do not assume that the MBSE Lite application source repository exists at any relative path from this project.
- If a missing capability requires a reusable MBSE Lite application change, treat that as a separate application-development task rather than editing outside this project root.
- External files referenced as project context or provenance are read-only by default; do not modify them unless an explicit project rule authorizes that write.
- Host metadata such as a future `00_INFO/` workspace descriptor is not engineering model content and must not be used to invent or duplicate MBSE facts.

## Portability

The project may move between repository-local storage and external domain storage without changing its engineering identity. When stable `project_id` support is available, preserve that identity across directory moves or renames.

Folder numbering or host conventions such as `XX_MBSE` are container metadata only and must not be treated as model identity.
