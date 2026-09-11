# Codex Instructions — Garden Tool Shed MBSE

## Scope

This directory contains the engineering/system model only.

## Belongs here

- stakeholder/user needs,
- system requirements,
- functions,
- logical/physical parts,
- solution concepts,
- technical decisions,
- verification definitions,
- technical assumptions and supporting engineering data,
- engineering issues and technical risks,
- relations between engineering objects.

## Does not belong here

Do not place task ownership, schedules, estimates, deadlines or milestone tracking here. Those belong in `../project_management/`.

## Engineering rules

- Preserve stable IDs.
- Separate needs from requirements and requirements from proposed solutions.
- Record important technical choices as `DEC-*` with rationale.
- Keep unknown technical facts as `TBD` or `ISSUE-*`; do not guess.
- When adding a requirement, define or plan its verification.
- Keep engineering-to-engineering relations in `07_relations.md` where practical.
- A project-management task may reference an engineering object without moving that engineering object out of this directory.
