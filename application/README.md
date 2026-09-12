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
- generate and render conceptual GLB engineering views with selection synchronized through the same stable model IDs,
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
    ├── floorplan.svg             # garden_tool_shed
    └── model.glb                 # garden_tool_shed
```

Generate without opening the browser:

```bash
uv run mbse-lite view ../projects/garden_tool_shed --no-open
```

Or choose an explicit output path:

```bash
uv run mbse-lite view ../projects/garden_tool_shed --output ../generated/garden_tool_shed/viewer.html
```

The viewer is read-only. Markdown remains the source of truth; every file in the viewer bundle is derived and disposable. No continuously running Python server or database is required. Navigation comes from `viewer.json`, while `model.json` carries the renderer-neutral objects, relations, supporting tables and validation results. Text view assets, including sanitized SVG, are embedded in the HTML. GLB assets used by `gltf` views are embedded separately as base64 and reconstructed as an `ArrayBuffer`, so direct `file://` use does not fetch the sibling binary file.

SVG elements use `data-mbse-id`; glTF nodes use `extras.mbse_id`. Clicking either interactive representation selects the same object used by the list and detail panel, while selecting elsewhere highlights the matching representation when that view is active. Three.js r180, `GLTFLoader` and `OrbitControls` load from a pinned jsDelivr ES-module mapping. If those modules are unavailable, the 3D view shows a useful message and all data, SVG and system views remain usable. Fully offline Three.js bundling is a future improvement.

The garden-shed floor plan and 3D model are conceptual. Its approximate project footprint sets the envelope proportions. The shared visualization-only layout spec uses a 2.2 m display height, 0.06 m wall thickness, 0.08 m floor thickness, 1.85 m display door height, 0.8 m ramp length, a 22% mower-zone split and an 11% shelving-length allocation where project geometry is unresolved. These values are presentation defaults, are not construction-ready, and are never written into project Markdown.

See `docs/VIEW_ARCHITECTURE.md` for the V0.3 manifest schema, SVG/glTF identity rules, binary transport, renderer lifecycle and object-selection contracts.

## Documentation

- `docs/MBSE_METHOD.md` — supported MBSE-lite model vocabulary and rules.
- `docs/APP_REQUIREMENTS.md` — requirements for the application itself.
- `docs/DEVELOPMENT_RULES.md` — rules for evolving the toolkit.
- `docs/VIEW_ARCHITECTURE.md` — generated view manifest and renderer contracts.

Project-specific engineering information does not belong in this directory.
