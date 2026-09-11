# Technical Projects

Each subdirectory under `projects/` is an independent technical project using MBSE Lite.

## Projects

- `demo_project/` — stable regression/demo model for application testing; intentionally retained in the older flat layout to exercise backwards compatibility.
- `garden_tool_shed/` — first real engineering project using separated MBSE and project-management areas.
- `_template/` — starting template for new projects.

## Isolation rule

A project's engineering facts, assumptions, requirements, decisions, risks and tasks belong only to that project. Do not reuse content from another project unless explicitly instructed.

## Recommended project structure

New projects should separate system engineering from project execution:

```text
projects/<project_name>/
├── README.md
├── AGENTS.md
├── mbse/
│   ├── AGENTS.md
│   ├── needs / requirements / functions
│   ├── architecture / concepts / decisions
│   ├── verification
│   ├── engineering issues and risks
│   └── engineering relations and supporting data
└── project_management/
    ├── AGENTS.md
    ├── tasks
    ├── milestones
    └── project-management / cross-area relations
```

The distinction is semantic, not merely organizational:

- `mbse/` defines the system and its engineering evidence,
- `project_management/` defines the work required to develop and deliver it.

Stable IDs and explicit relations may cross the boundary.

## Required project entry files

Every real project should have at least:

- `README.md` — purpose, scope and navigation,
- `AGENTS.md` — project-level Codex instructions.

`projects/_template/` provides the recommended starting point, not a mandatory rigid schema.

## Recommended lifecycle

1. Copy `_template/` to a new project directory.
2. Customize `README.md` and root `AGENTS.md` first.
3. Keep technical model content under `mbse/`.
4. Keep tasks, milestones and execution tracking under `project_management/`.
5. Add project-specific engineering files when useful.
6. Keep IDs unique across the whole project and relations compatible with the MBSE Lite model contract.

## Tool usage

From `application/`:

```bash
uv run mbse-lite validate ../projects/<project_name>
uv run mbse-lite view ../projects/<project_name>
uv run mbse-lite export-html ../projects/<project_name> ../generated/<project_name>/index.html
uv run mbse-lite export-xlsx ../projects/<project_name> ../generated/<project_name>/model.xlsx
```

MBSE Lite reads project Markdown recursively. Generated outputs should normally remain outside the project's authoritative Markdown model.
