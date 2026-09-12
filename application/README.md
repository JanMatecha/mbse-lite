# MBSE Lite Application

This directory contains only the reusable MBSE Lite toolkit and its development documentation.

## Purpose

The application reads Markdown-based project models, validates IDs and relations, and generates alternative views and exchange formats.

Current POC capabilities:

- parse Markdown tables,
- retain table, row, object, relation and per-attribute source provenance,
- build an internal object/relation model,
- validate IDs and traceability,
- generate Mermaid traceability views,
- generate static HTML overview,
- generate and open a manifest-driven, multi-view read-only web viewer,
- generate interactive, selection-synchronized SVG engineering views when a domain generator matches the model,
- generate and render conceptual GLB engineering views with selection synchronized through the same stable model IDs,
- export LibreOffice-compatible XLSX,
- import XLSX into a reviewable Markdown directory,
- safely update one existing Markdown object attribute with optimistic concurrency and validation,
- parse explicitly sourced structured geometry quantities with deterministic decimal values,
- optionally export a footprint-only STEP plus separately classified conceptual CadQuery artifacts.

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

Safely preview or apply one existing attribute update:

```bash
uv run mbse-lite update-attribute ../projects/demo_project PART-001 Description "Revised description" --expect "Current description" --dry-run
uv run mbse-lite update-attribute ../projects/demo_project PART-001 Description "Revised description" --expect "Current description"
```

The command resolves the exact Markdown cell from parser provenance, re-locates the row by stable ID, validates a temporary candidate project, and commits atomically. `--expect` rejects stale values and `--dry-run` never changes a file. Generic updates cannot change the `ID` column.

## Optional CadQuery export

Normal installation and every non-CAD command remain independent from CadQuery. To work on the optional CAD path, use a separate environment with Python 3.12 and install both extras:

```bash
uv sync --extra dev --extra cad
```

CadQuery 2.8.0 is selected exactly for this proof of concept. It is the stable release tested with `cadquery-ocp` 7.9.3.1.1. Although that OCP release publishes wheels for newer interpreters, CadQuery's pip installation guidance currently documents support only through Python 3.12, so the dedicated CAD CI job uses 3.12. The unchanged core CI job continues to use Python 3.13.

The evaluated Windows pip/uv environments successfully generated and verified every artifact but then failed nondeterministically during CadQuery/OCP interpreter teardown, with both `0xC0000005` access violations and the upstream `0xC0000374` shutdown defect tracked in [CadQuery issue #1911](https://github.com/CadQuery/cadquery/issues/1911). CAD now runs in a disposable child process, so the main CLI never imports CadQuery/OCP. After atomically publishing validated completion evidence and explicitly flushing its streams, a successful worker calls `os._exit(0)` before unstable native teardown begins. Exit `0` is therefore the expected Windows success path. `0xC0000005` is always rejected; the exact `0xC0000374` rule remains only as a strictly validated warning fallback. The Linux Python 3.12 CAD CI job remains the supported automated gate for V0.6.

Export the garden-shed CAD artifacts:

```bash
uv run mbse-lite export-cad ../projects/garden_tool_shed ../generated/garden_tool_shed/cad
```

The command validates the full model and visualization profile before launching the isolated CAD worker. Validation errors stop export. If CadQuery is absent, the command reports the optional-install command without exposing a raw import traceback.

The output contains:

```text
generated/garden_tool_shed/cad/
├── footprint.step             # engineering authority: footprint only
├── conceptual-preview.step    # visualization-only
├── conceptual-preview.glb     # visualization-only
├── cad-manifest.json          # generated metadata, not source of truth
└── cad-job-result.json        # atomic worker-completion evidence
```

`footprint.step` is a planar 4000 mm × 1200 mm CAD face sourced from the structured REQ-008 quantities. It has zero Z extent: no height or material thickness is inferred. The two conceptual previews reuse that footprint and the explicitly mapped PART identities, but all unresolved height, wall, floor, door, ramp, shelving and layout values come only from `GardenShedVisualizationSpec` and remain non-authoritative.

CadQuery 2.8.0 preserves the seven direct assembly PART names through STEP re-import and as GLB node names in the tested export. Its GLB does not emit the current viewer's `extras.mbse_id` metadata, so `mbse-lite view` deliberately keeps its proven custom GLB generator and requires no CAD dependency. The parent accepts an export only after cross-checking the job-specific completion record, artifact sizes, manifest, footprint extent and identity evidence. See `docs/CAD_ARCHITECTURE.md` for the process, authority, unit, manifest and identity contracts.

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
├── assets/
│   └── vendor/
│       ├── three-viewer-0.180.0.min.js
│       ├── mermaid-11.17.2.min.js
│       ├── manifest.json
│       └── *-LICENSE.txt
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

Browser startup goes through a read-only `EmbeddedDataProvider` with `{read: true, write: false}` capabilities. It supplies the embedded manifest, model snapshot, text assets, binary assets and asset errors to the unchanged renderer context. This boundary is designed for a future HTTP provider without introducing a server or network dependency into static mode. Generated `model.json` is a snapshot and must never be edited as a source of truth.

## Future editable serve mode

V0.5 documents but does not implement the future command:

```bash
mbse-lite serve ../projects/garden_tool_shed
```

That mode will run on local HTTP, load snapshots through a future `HttpDataProvider`, and route every write through the validated application command layer to Markdown before reloading and validating the project. The server framework remains unspecified and replaceable. Static `mbse-lite view` remains `file://`, embedded and read-only; both modes use the same authoritative Markdown project.

SVG elements use `data-mbse-id`; glTF nodes use `extras.mbse_id`. Clicking either interactive representation selects the same object used by the list and detail panel, while selecting elsewhere highlights the matching representation when that view is active. A 5-pixel movement threshold distinguishes selection clicks from orbit drags.

Core browser dependencies are local and pinned: Three.js `0.180.0` (including bundled `GLTFLoader` and `OrbitControls`) and Mermaid `11.17.2`. Generation copies classic-script builds from Python package resources to `assets/vendor/`; classic scripts avoid local ES-module imports that some browsers reject under `file://`. If a local dependency is missing or a view asset is malformed, that view shows a localized message while unrelated views remain usable.

The garden-shed project opts into its generator through `projects/garden_tool_shed/visualization.md`. Its reserved Markdown table maps `Visualization Profile` + `Role` to an existing `Object ID` and `Expected Type`. In addition to the modeled parts and structured footprint source, the explicit `mower_door_candidate` and `main_door_candidate` roles select the only Concepts used in displayed-candidate metadata. The mapping supplies visualization semantics only; it neither duplicates nor changes the engineering definition. Missing objects, wrong types and missing generator-required roles fail validation clearly. A project without the `garden_shed` profile does not activate those views.

The garden-shed floor plan and 3D model are conceptual. The `footprint` profile role maps to REQ-008, whose structured `Target Length [m]` and `Target Depth [m]` attributes become provenance-carrying `Quantity` values and then `GardenShedGeometrySpec.external_length` and `.external_depth`. `GardenShedVisualizationSpec` consumes that engineering spec. It separately owns the 2.2 m display height, 0.06 m wall thickness, 0.08 m floor thickness, 1.85 m display door height, 0.8 m ramp length, 22% mower-zone split and 11% shelving-length allocation where project geometry is unresolved. These presentation defaults remain outside the authoritative geometry spec, are not construction-ready and are never written into project Markdown.

## Updating offline viewer assets

The checked-in assets and integrity manifest are rebuilt only when intentionally upgrading a dependency:

```bash
cd tools/viewer-assets
npm ci
npm run build
```

`package-lock.json` pins the complete update toolchain, including esbuild `0.25.9`. Normal Python installation, testing and viewer generation do not require Node. Three.js and Mermaid are MIT-licensed; their license files are packaged and copied beside the browser assets. Dependency upgrades must retain upstream notices and recheck licenses, including Mermaid's bundled transitive code.

See `docs/VIEW_ARCHITECTURE.md` for the V0.5 manifest schema, source provenance, offline packaging, visualization-profile, SVG/glTF identity, binary transport, renderer lifecycle and object-selection contracts.

## Documentation

- `docs/MBSE_METHOD.md` — supported MBSE-lite model vocabulary and rules.
- `docs/APP_REQUIREMENTS.md` — requirements for the application itself.
- `docs/DEVELOPMENT_RULES.md` — rules for evolving the toolkit.
- `docs/VIEW_ARCHITECTURE.md` — generated view manifest and renderer contracts.
- `docs/CAD_ARCHITECTURE.md` — optional CadQuery adapter, authority and artifact contracts.

Project-specific engineering information does not belong in this directory.
