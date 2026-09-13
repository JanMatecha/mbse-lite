# Technical Projects

The `projects/` directory contains repository-local technical projects, fixtures and the reusable starting template for MBSE Lite.

## Current contents

- `demo_project/` — stable regression/demo model for application testing; intentionally retained in the older flat layout to exercise backwards compatibility.
- `garden_tool_shed/` — first real engineering project using separated MBSE and project-management areas; currently retained as an authoritative real project because it is also an integration/regression case for application development.
- `_template/` — starting template for a new MBSE Lite project root.

## Current versus target role of this directory

During active application development, a real project may live under `projects/` when it provides important integration and regression coverage. For such a project, the Markdown in that directory remains authoritative until an explicit migration is performed.

Long term, `projects/` is not intended to be the mandatory production storage location for every real project. The target repository role is primarily:

- `_template/`,
- demo/synthetic fixtures,
- deliberately retained integration fixtures.

A real project's authoritative MBSE workspace may instead live in external domain storage and be opened by passing its project-root path to MBSE Lite.

For the planned Family KB integration, a real project may be hosted as `<DOMAIN>/<TOPIC>/<PROJECT>/XX_MBSE/`. `XX_MBSE` is the MBSE Lite project root and an application-workspace boundary; the `XX` prefix is host ordering only and must not become application identity.

Do not keep an authoritative repository copy and an authoritative external copy in parallel. Migration is a deliberate one-time switch of authority after the external project-root contract is ready and validated.

## Isolation rule

A project's engineering facts, assumptions, requirements, decisions, risks and tasks belong only to that project. Do not reuse content from another project unless explicitly instructed.

External context may eventually be referenced explicitly, but reference/provenance is not permission to duplicate or modify the source.

## Recommended project structure

New projects should separate system engineering from project execution, regardless of where the project root is stored:

```text
<project_root>/
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

An external host knowledge base may add host metadata beside these areas, for example `00_INFO/` at the project root. Such metadata is not MBSE model content. V0.10 still scans Markdown recursively; explicit model roots that safely exclude host metadata are a guiding requirement for the portable target architecture.

## Required project entry files

Every real project should have at least:

- `README.md` — purpose, scope and navigation,
- `AGENTS.md` — project-level AI/agent instructions.

`projects/_template/` provides the recommended starting point, not a mandatory rigid schema and not a requirement that the resulting project remain inside this repository.

## Recommended lifecycle

1. Copy `_template/` to the chosen project root, either repository-local or external.
2. Customize `README.md` and root `AGENTS.md` first.
3. Keep technical model content under `mbse/`.
4. Keep tasks, milestones and execution tracking under `project_management/`.
5. Add project-specific engineering files when useful.
6. Keep IDs unique across the whole project and relations compatible with the MBSE Lite model contract.
7. If the project later changes authoritative storage, migrate once, validate the moved model and explicitly retire the old authoritative copy.

## Tool usage

From `application/`, repository-local examples are:

```bash
uv run mbse-lite validate ../projects/<project_name>
uv run mbse-lite view ../projects/<project_name>
uv run mbse-lite serve ../projects/<project_name>
uv run mbse-lite export-html ../projects/<project_name> ../generated/<project_name>/index.html
uv run mbse-lite export-xlsx ../projects/<project_name> ../generated/<project_name>/model.xlsx
```

The `project` argument is a path, so the same commands may point to an external project root.

MBSE Lite V0.10 reads project Markdown recursively. Generated outputs should normally remain outside the project's authoritative Markdown model.
