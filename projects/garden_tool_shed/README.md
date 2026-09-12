# Garden Tool Shed

First real MBSE-lite project used to develop and validate the method on a private technical project.

## Project goal

Develop a sufficiently complete concept and technical definition for a garden tool shed so that it can proceed into detailed design and construction.

## Current phase

Initial problem definition, requirements capture and concept development.

## Source of truth

The Markdown files in this project are authoritative project data. Generated HTML, Mermaid and XLSX files are views or exchange formats only.

## Separation of MBSE and project management

This project deliberately separates system engineering from delivery planning:

```text
garden_tool_shed/
├── mbse/                 # what/why/how the shed shall work
├── project_management/   # work needed to develop and deliver it
└── visualization.md      # non-engineering role mapping for generated views
```

### `mbse/`

Contains needs, requirements, functions, architecture, concepts, technical decisions, verification, engineering issues and supporting engineering data.

### `project_management/`

Contains tasks, milestones and relations that connect project work to engineering objects.

Project-management files may reference stable MBSE IDs, but they must not duplicate or redefine engineering facts.

## Working rule

Do not invent dimensions, materials, loads, budget, legal constraints or other technical facts. Unknown technical values must be recorded as `TBD` or as an engineering `ISSUE` until confirmed.

## Main model files

Engineering model:

- `mbse/01_needs.md`
- `mbse/02_requirements.md`
- `mbse/03_functions.md`
- `mbse/04_architecture_and_concepts.md`
- `mbse/05_verification.md`
- `mbse/06_engineering_issues.md`
- `mbse/07_relations.md`
- `mbse/08_inventory.md`

Project management:

- `project_management/01_tasks.md`
- `project_management/02_milestones.md`
- `project_management/03_relations.md`

Visualization metadata:

- `visualization.md` — maps semantic visualization roles, including the structured footprint source and two geometry-relevant candidate Concepts, to existing stable MBSE IDs; it does not redefine engineering objects or make generated geometry authoritative.

The structure may be extended when the project needs additional dedicated files such as site data, calculations, drawings, BOM or construction planning.
