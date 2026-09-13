# mbse-lite

This repository intentionally separates reusable application development from engineering project data:

1. `application/` — development of the MBSE Lite Python toolkit.
2. `projects/` — repository-local technical projects, fixtures and templates used while the toolkit evolves.

The separation is deliberate: application development must not silently change project engineering data, and project work must not silently change the application.

## Current repository structure

```text
mbse-lite/
├── AGENTS.md
├── README.md
├── application/
│   ├── AGENTS.md
│   ├── README.md
│   ├── docs/
│   ├── src/
│   ├── tests/
│   └── pyproject.toml
└── projects/
    ├── README.md
    ├── _template/
    ├── demo_project/
    └── garden_tool_shed/
```

## Current versus target project storage

### Current state

Repository-local projects under `projects/` are currently authoritative for the engineering data they contain. Real projects may remain here while they are actively useful for application development, regression testing and integration validation.

This is a transitional development arrangement, not a requirement that every future MBSE Lite project must live inside this repository.

### Target state

MBSE Lite is intended to work on a project root supplied by path, independent of the location or name of the containing directory. The application repository should eventually contain primarily:

- reusable application code,
- documentation,
- `_template/`,
- demo/synthetic fixtures,
- integration fixtures that are intentionally retained for application testing.

Real project authority may then live in the project's natural domain storage instead of in the application repository.

For the planned Family KB integration, the host-side pattern is:

```text
<DOMAIN>/
└── <TOPIC>/
    └── <PROJECT>/
        ├── 00_INFO/
        ├── XX_PHOTOS/
        ├── XX_COMMUNICATION/
        ├── XX_DOCUMENTS/
        └── XX_MBSE/              # MBSE Lite project root / workspace boundary
            ├── 00_INFO/          # host metadata for the workspace boundary
            ├── README.md
            ├── AGENTS.md
            ├── mbse/
            └── project_management/
```

`XX` is host-side ordering only. MBSE Lite must not depend on a fixed number, folder name or absolute path for project identity.

The migration of a real project out of `projects/` is intended to be a one-time switch of authority after technical readiness criteria are met. The design explicitly avoids a long-running two-master synchronization model between the repository copy and the external authoritative project.

## Application development

Work on the toolkit in `application/` and follow `application/AGENTS.md`.

```bash
cd application
uv sync --extra dev
uv run pytest -q
uv run mbse-lite validate ../projects/demo_project
```

## Project work

A project has its own `README.md` and `AGENTS.md`; project-specific instructions take precedence inside that project root.

For repository-local work, create a project or fixture from `projects/_template/`. For an external real project, use the same project-root contract at the chosen external location and invoke MBSE Lite with that path.

The current CLI and local server already receive the project directory as an explicit path. V0.10 still scans Markdown recursively beneath that root; the target architecture adds explicit model roots, stable project identity and controlled read-only access to selected context outside the writable project root.

## Source of truth

Authoritative engineering content is Markdown inside the declared MBSE Lite project model. Mermaid, HTML, SVG, GLB, STEP and XLSX are generated views or exchange formats unless a project explicitly documents a narrower engineering-authority role for a generated artifact.

The generated interactive viewer is self-contained for normal direct-file use: it copies pinned Mermaid and Three.js browser assets into its `assets/` directory and does not require a CDN or a continuously running server. Projects may opt into domain visualizations through Markdown visualization profiles that map semantic roles to existing stable MBSE IDs without redefining the engineering objects.

## Target project-root contract

The future portable project-root contract is guiding architecture, not fully implemented in V0.10. It includes:

- a stable `project_id` independent of filesystem path and directory name,
- explicit authoritative model roots such as `mbse/` and `project_management/`, so host metadata such as `00_INFO/` cannot be mistaken for model objects,
- writes constrained to the project workspace,
- explicitly declared external context that may be read but is read-only by default,
- provenance/reference links from MBSE objects to supporting files outside the workspace without duplicating their content,
- semantic changesets for controlled writes in addition to underlying file/version history.

The detailed guiding requirements are tracked in `application/docs/APP_REQUIREMENTS.md` and the method boundary is described in `application/docs/MBSE_METHOD.md`.

## Privacy

Do not copy technical facts, examples, assumptions, customer information or private data between projects unless explicitly requested. Check repository visibility before adding sensitive project data.
