# mbse-lite

This repository intentionally contains two separated areas:

1. `application/` — development of the MBSE Lite Python toolkit.
2. `projects/` — independent technical projects that use the toolkit.

The separation is deliberate: application development must not silently change project engineering data, and project work must not silently change the application.

## Repository structure

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
    └── demo_project/
```

## Application development

Work on the toolkit in `application/` and follow `application/AGENTS.md`.

```bash
cd application
uv sync --extra dev
uv run pytest -q
uv run mbse-lite validate ../projects/demo_project
```

## Project work

Each project is isolated under `projects/<project_name>/` and has its own `README.md` and `AGENTS.md`. Project-specific instructions take precedence inside that project directory.

Create a new project by copying `projects/_template/` and then tailoring its files and local Codex instructions.

## Source of truth

For each technical project, Markdown files inside that project directory are the source of truth. Mermaid, HTML and XLSX are generated views or exchange formats.

## Privacy

Do not copy technical facts, examples, assumptions, customer information or private data between projects unless explicitly requested. Check repository visibility before adding sensitive project data.
