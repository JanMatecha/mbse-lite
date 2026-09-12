# Optional CAD Architecture — V0.7

## Scope

V0.7 adds one narrow identity-contract bridge to the isolated CAD path without replacing the production viewer GLB or claiming a complete shed CAD model:

```text
authoritative project Markdown
        ↓ parse and validate
Model + Decimal Quantity provenance
        ↓
GardenShedGeometrySpec
        ↓ serialize validated job
pure parent runner
        ↓ child process (`python -m mbse_lite.cad.worker`)
CadQuery adapter (internal unit: mm)
        ↓
raw conceptual GLB
        ↓ pure-Python identity bridge
final conceptual GLB with `node.extras.mbse_id`
        ↓
footprint STEP + conceptual STEP/GLB + manifest + completion record
```

`mbse_lite.geometry`, `mbse_lite.cad.protocol`, `mbse_lite.cad.glb_identity` and `mbse_lite.cad.runner` have no CadQuery dependency. The main process validates the model and serializes a job; only `mbse_lite.cad.worker` imports `mbse_lite.cad.cadquery_backend`, and only that backend imports CadQuery. Importing MBSE Lite, importing the public CAD package, or invoking any CLI command never loads CadQuery/OCP into the main process.

## Installation and interpreter choice

CadQuery is isolated in the `cad` optional dependency group:

```bash
uv sync --extra dev --extra cad
```

V0.6 selects `cadquery==2.8.0`, the current stable release evaluated for this implementation. The tested dependency resolution uses `cadquery-ocp==7.9.3.1.1`. OCP publishes wheels for Python 3.12, 3.13 and 3.14 on the evaluated platforms, but CadQuery's own pip installation text currently documents support only through Python 3.12. The separate CAD CI job therefore uses Python 3.12; normal CI remains on Python 3.13 and does not install the extra.

On the evaluated Windows host, CadQuery/OCP generated and semantically verified all artifacts but failed nondeterministically during interpreter teardown. An initial reproduction ended with heap-corruption status `0xC0000374`; a five-run worker reliability check later produced four access violations (`0xC0000005`) and one heap-corruption exit. Neither native status is a reliable normal completion mechanism. A minimal `import cadquery` also reproduces the upstream shutdown problem tracked in [CadQuery issue #1911](https://github.com/CadQuery/cadquery/issues/1911).

The disposable worker now deliberately calls `os._exit(0)` after successful publication and explicit stream flushing, before Python starts CadQuery/OCP teardown. It also disables interactive Windows fault dialogs defensively so a native failure before controlled termination produces a process status instead of hanging behind crash UI. `0xC0000005` is never accepted. The narrow `0xC0000374` rule remains only as a defensive compatibility fallback; it is no longer the expected success path. The Linux Python 3.12 CAD job remains the V0.6 CI gate, and a conda-based CadQuery environment remains the documented upstream fallback for other Windows CadQuery use.

If the optional import is missing or cannot load its binary runtime, the CLI returns:

```text
CadQuery support is not installed.
Install the optional CAD dependencies with: uv sync --extra cad
```

## Parent runner, worker and unit boundary

The public parent-side API is intentionally small:

- `quantity_to_millimetres(Quantity) -> Decimal`
- `export_project_cad(Model, output_dir) -> CadExportResult`

The worker-only backend owns footprint/preview construction and STEP/GLB inspection helpers. The parent calls the worker with `sys.executable` by default so it uses the selected application environment; callers may explicitly provide another Python executable. The job is JSON containing a unique job ID, resolved output directory, source-provenanced quantities, stable role IDs, visualization-only defaults and the exact expected footprint extent. No live model object or CadQuery object crosses the process boundary.

Authoritative `Quantity` values stay as `Decimal` through conversion. Supported length units are `m` and `mm`; other units fail explicitly. The adapter converts metres to millimetres once and converts to `float` only at calls into CadQuery. Visualization-only metre values pass through the same labeled conversion boundary but never enter `GardenShedGeometrySpec`.

## Authority levels

Authoritative engineering data:

- project Markdown;
- REQ-008 structured `Target Length [m]` and `Target Depth [m]` cells and their source references;
- `GardenShedGeometrySpec`;
- `footprint.step`, only within its stated `footprint-only` scope.

Non-authoritative visualization data:

- every unresolved default in `GardenShedVisualizationSpec`;
- `conceptual-preview.step`;
- `conceptual-preview.glb`;
- conceptual component positions, proportions and presentation geometry.

Generated, non-authoritative metadata:

- `cad-manifest.json`;
- `cad-job-result.json`;
- all STEP and GLB serialization details outside the explicit footprint-only scope.

## Authoritative footprint representation

The authoritative artifact is a rectangular CadQuery `Face` on the XY plane. Its current extents are 4000 mm × 1200 mm × 0 mm. A face is used because it exports and re-imports through STEP without adding a solid thickness. The source values come only from the explicitly mapped footprint Requirement. Free Requirement prose is never parsed as geometry, and no fallback to visualization defaults exists.

This artifact does not define height, wall/floor/roof thickness, roof shape, doors, shelves, ramp, structure, materials or tolerances.

## Conceptual preview

The conceptual assembly represents the existing visualization roles for PART-001, PART-004, PART-005, PART-008, PART-010, PART-011 and PART-012. The authoritative length and depth come through `GardenShedGeometrySpec`; unresolved 3D values come from `GardenShedVisualizationSpec` and are written to the manifest under `visualization_only_inputs`.

Each direct CadQuery assembly child is named with its mapped stable PART ID. After CadQuery export, the dependency-free GLB bridge receives the exact component mapping from the CAD job-derived preview, requires exactly one matching node per expected name, and adds the same stable ID as `node.extras.mbse_id`. It merges existing extras, rejects conflicts or unexpected identity metadata, preserves every non-JSON chunk byte-for-byte, and atomically replaces the GLB before re-reading it for semantic validation. Candidate metadata still comes only from the explicit `mower_door_candidate` and `main_door_candidate` roles. Adding an unrelated preferred Concept cannot affect the assembly component set.

The browser identity path is therefore:

```text
CadQuery assembly node name
        ↓ GLB identity bridge
glTF node.extras.mbse_id
        ↓ GLTFLoader
Three.js Object3D.userData.mbse_id
        ↓
existing MBSE Lite selection contract
```

`node.name` remains useful export evidence and supports `getObjectByName`, but it is not the authoritative browser selection contract. The explicit selection identity is `extras.mbse_id` / `userData.mbse_id`.

## Artifact manifest

`cad-manifest.json` schema `0.6` records:

- backend name/version and internal length unit;
- each file's format, authority and scope;
- footprint extents and source object ID;
- original engineering quantities with Markdown cell provenance;
- all visualization-only defaults used by the conceptual preview;
- requested in-memory component names and identity observed after STEP/GLB export, including both exact GLB node names and `extras.mbse_id` values.

The V0.7 result changes the truth value of existing schema `0.6` identity evidence; it does not add or remove manifest fields, so no manifest schema bump is required.

The manifest is reproducible generated metadata. It is not read back as project input and cannot override Markdown.

## Completion protocol and exit classification

The worker publishes `cad-job-result.json` with a temporary sibling file plus `os.replace`, and only after all four required artifacts are in their final locations. The record includes the unique job ID, exact artifact sizes, backend identity, stable IDs and mandatory semantic-check results. Before publishing it, the worker:

- re-imports `footprint.step` and verifies its requested X/Y extents and zero Z extent;
- verifies every required artifact is present and non-empty;
- verifies all seven stable component IDs survived STEP re-import and GLB node export as both node names and matching `extras.mbse_id` values;
- writes the complete authority/provenance manifest.

The result file is closed and `fsync` completes before its atomic publication. After publication, the worker explicitly flushes stdout and stderr and immediately invokes `os._exit(0)`. That real process-level exit is confined to the disposable native CAD worker; worker unit tests replace it with a mock. It is not used by the CLI parent, normal application code, or any future server process, and it is unreachable on every failure path. This intentionally skips Python `atexit` handlers and CadQuery/OCP interpreter teardown only after MBSE Lite has finished, closed and published all success evidence.

The parent removes any old completion record before launch, then validates the new record's schema and exact job ID. It independently checks each recorded file and size, parses the final GLB without CadQuery, compares its name/extras pairs with the explicit job identities and completion evidence, and checks the requested footprint extent, manifest authority/scope/provenance and backend metadata. A stale record, a record written before the current job, a missing/empty/changed artifact, identity tampering, or a failed semantic check cannot establish success.

Exit classification is deliberately exact:

- controlled worker exit code `0` plus a fully valid completion record is the expected success path on Windows and other platforms;
- on Windows only, `0xC0000374` (including its signed process-code representation `-1073740940`) plus that same fully valid record remains success with a warning as a defensive fallback;
- every other nonzero exit is failure, even if files or a completion record exist;
- a missing or invalid completion record is failure for every exit code, including `0` and the known Windows code;
- `0xC0000005` access violations are always failures, and the `0xC0000374` exception is never accepted on Linux or another platform.

## Stable identity contract

With CadQuery 2.8.0/OCP 7.9.3.1.1, the seven direct PART names survive semantic STEP assembly re-import and appear as exact raw GLB node names. CadQuery does not emit `node.extras.mbse_id`, so the V0.7 bridge adds that metadata only for the explicit expected component mapping. It never infers authority from a name pattern or scans arbitrary `PART-*` names.

The resulting GLB now satisfies the current viewer identity contract, but V0.7 deliberately leaves `mbse-lite view`, its deterministic custom `views/model.glb`, and its selection behavior unchanged. The CadQuery GLB also remains millimetre-scaled (approximately 4000 × 2220 × 1997), unlike the approximately metre-scaled production viewer GLB. Scaling and production integration remain future work.

## Validation, writes and determinism

`export-cad` loads the model, runs core and visualization validation, resolves the explicit garden-shed profile and builds the job before launching the worker. ERROR findings stop the operation without launching a child. Worker files are generated in a temporary directory beneath the target and moved into place only after export and semantic inspection succeed; the atomic completion record is published last, streams are flushed explicitly, and the worker then terminates without entering native interpreter teardown.

Tests assert semantic determinism rather than byte equality: dimensions, shape type, zero Z extent, component set, classifications, provenance and observed stable IDs. Exporter ordering or binary metadata is not treated as engineering meaning.

## Future direction

Later versions may move a dimension from visualization-only state into structured Markdown only after a requirement or decision defines it. CadQuery can then consume the new typed domain value through the same unit boundary. Any future `serve` implementation must invoke the pure parent runner; it must never import or call the CadQuery backend in the long-running server process. Future production-viewer integration must explicitly resolve the known scaling difference; it must not infer missing geometry or replace Markdown as the source of truth.
