# Codex Instructions — Garden Tool Shed Project Management

## Scope

This directory contains planning and tracking of project work, not the technical definition of the shed.

## Belongs here

- `TASK-*` work items,
- `MS-*` milestones,
- owners, estimates, deadlines and status,
- project-management relations to engineering objects,
- delivery/project risks or issues if they are genuinely about execution rather than the system design.

## Rules

- Do not redefine needs, requirements, architecture or technical decisions here.
- Reference stable IDs from `../mbse/` instead of copying engineering facts.
- Use `03_relations.md` for links such as `TASK -> ISSUE`, `TASK -> VER` or other work-to-engineering traceability.
- Keep engineering issues in `../mbse/`; create a task here when work is needed to resolve them.
- Do not modify `../mbse/` during ordinary project-planning updates unless the user explicitly asks for an engineering change too.
