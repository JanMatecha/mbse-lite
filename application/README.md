# MBSE Lite Application

This directory contains only the reusable MBSE Lite toolkit and its development documentation.

## Purpose

The application reads Markdown-based project models, validates IDs and relations, and generates alternative views and exchange formats.

Current POC capabilities:

- parse Markdown tables,
- build an internal object/relation model,
- validate IDs and traceability,
- generate Mermaid traceability views,
- generate static HTML overview,
- generate and open a manifest-driven, multi-view read-only web viewer,
- generate interactive, selection-synchronized SVG engineering views when a domain generator matches the model,
- export LibreOffice-compatible XLSX,
- import XLSX into a reviewable Markdown directory.

## Development setup

From this directory:

```bash
uv sync --extra dev
uv run pytest -q
```

Validate the repository demo project:

```bash
uv run mbse-lite validate ../projects/demo_project
```

Generate outputs:

```bash
uv run mbse-lite export-mermaid ../projects/demo_project ../generated/demo_traceability.md
uv run mbse-lite export-html ../projects/demo_project ../generated/demo_index.html
uv run mbse-lite export-xlsx ../projects/demo_project ../generated/demo_model.xlsx
```

## Local web viewer

Generate the interactive viewer and open it in the default browser:

```bash
uv run mbse-lite view ../projects/demo_project
```

For the garden-tool-shed project:

```bash
uv run mbse-lite view ../projects/garden_tool_shed
```

By default the viewer bundle is written under `../generated/<project-name>/` when the project is under the repository `projects/` directory:

```text
generated/<project-name>/
├── index.html
├── model.json
├── viewer.json
└── views/
    ├── traceability.mmd
    ├── delivery-traceability.mmd
    └── floorplan.svg             # garden_tool_shed
```

Generate without opening the browser:

```bash
uv run mbse-lite view ../projects/garden_tool_shed --no-open
```

Or choose an explicit output path:

```bash
uv run mbse-lite view ../projects/garden_tool_shed --output ../generated/garden_tool_shed/viewer.html
```

The viewer is read-only. Markdown remains the source of truth; every file in the viewer bundle is derived and disposable. No continuously running Python server or database is required. Navigation comes from `viewer.json`, while `model.json` carries the renderer-neutral objects, relations, supporting tables and validation results. Text view assets, including sanitized SVG, are also embedded in the HTML so direct `file://` use remains possible. Clicking an SVG element with `data-mbse-id` selects the same object used by the list and detail panel; selection elsewhere highlights matching SVG elements. Mermaid rendering uses a CDN when internet access is available; its source and the rest of the viewer remain usable offline.

The garden-shed floor plan is conceptual. Its approximate project footprint sets only the outer aspect ratio; unresolved internal positions and sizes are clearly labeled visualization-only and are not written into project Markdown.

See `docs/VIEW_ARCHITECTURE.md` for the V0.2 manifest schema, SVG identity/sanitization rules, renderer and object-selection contracts, and the current `mermaid`, `graph`, `svg` and `gltf` support boundary.

## Documentation

- `docs/MBSE_METHOD.md` — supported MBSE-lite model vocabulary and rules.
- `docs/APP_REQUIREMENTS.md` — requirements for the application itself.
- `docs/DEVELOPMENT_RULES.md` — rules for evolving the toolkit.
- `docs/VIEW_ARCHITECTURE.md` — generated view manifest and renderer contracts.

Project-specific engineering information does not belong in this directory.
