# Codex Instructions — Application Development

## Scope

These instructions apply to `application/` only. This directory contains reusable software, tests and application-level documentation. Do not place project-specific engineering facts here.

## Architecture principles

- Markdown project files are the authoritative project model.
- Python parses and validates the Markdown model.
- Relations are explicit and machine-readable.
- Mermaid, HTML and XLSX are generated views/exchange formats.
- Keep the implementation small, transparent and easy to inspect.
- Keep future SysML v2 mapping possible, but do not implement a full SysML parser unless explicitly required.

## Development rules

- Add or update automated tests whenever parser, validation, import/export or relation behavior changes.
- Prefer explicit data structures over unnecessary abstractions.
- Do not add a database, server, web framework or heavy dependency without a demonstrated project need.
- Do not silently change the Markdown model contract; document model-format changes in `docs/MBSE_METHOD.md`.
- Application requirements belong in `docs/APP_REQUIREMENTS.md`, not in technical project requirement files.
- Preserve backwards compatibility for existing project Markdown when practical.
- Treat `../projects/demo_project` as a regression fixture, not as a place for real private project data.

## Workflow for a new capability

1. Identify the reusable need from project usage.
2. Add/update an `APP-REQ-*` entry when the capability is material.
3. Add a failing or representative test.
4. Implement the smallest useful change.
5. Run the complete application test suite.
6. Validate `../projects/demo_project`.
7. Update documentation if CLI behavior or the model contract changed.

## Quality gates

Before considering an application change complete:

```bash
uv run pytest -q
uv run mbse-lite validate ../projects/demo_project
```

Do not edit unrelated project files to make these checks pass.
