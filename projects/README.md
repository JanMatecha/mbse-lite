# Technical Projects

Each subdirectory under `projects/` is an independent technical project using MBSE Lite.

## Isolation rule

A project's engineering facts, assumptions, requirements, decisions, risks and tasks belong only to that project. Do not reuse content from another project unless explicitly instructed.

## Required project entry files

Every real project should have at least:

- `README.md` — purpose, scope and navigation,
- `AGENTS.md` — project-specific Codex instructions.

The remaining Markdown structure may be tailored to the project. `projects/_template/` provides the recommended starting point, not a mandatory rigid schema.

## Recommended lifecycle

1. Copy `_template/` to a new project directory.
2. Customize `README.md` and `AGENTS.md` first.
3. Remove sections/files the project does not need.
4. Add project-specific files when useful.
5. Keep IDs and relations compatible with the MBSE Lite model contract where machine validation/export is desired.

## Tool usage

From `application/`:

```bash
uv run mbse-lite validate ../projects/<project_name>
uv run mbse-lite export-html ../projects/<project_name> ../generated/<project_name>/index.html
uv run mbse-lite export-xlsx ../projects/<project_name> ../generated/<project_name>/model.xlsx
```

Generated outputs should normally remain outside the project's authoritative Markdown model.
