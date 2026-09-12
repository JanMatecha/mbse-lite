# View Architecture V0.4

## Purpose

A **View** is one representation of the shared MBSE Lite model. A view does not own engineering identity or become a second model: it references objects through the same stable IDs used in the authoritative Markdown.

View Architecture V0.4 separates three concerns:

1. Markdown parsing produces the internal MBSE model.
2. generation produces a renderer-neutral `model.json`, a navigation-oriented `viewer.json` and any view assets,
3. the browser chooses a renderer from each manifest entry's `type`.

The navigation and renderer choice therefore do not depend on a project name such as `garden_tool_shed`.

## Source of truth

Project Markdown remains authoritative. `index.html`, `model.json`, `viewer.json`, Mermaid, SVG, glTF/GLB and other viewer assets are generated, derived and disposable. Visualization must not silently create or change needs, requirements, decisions, geometry facts or project-management commitments.

## Generated bundle

The `view` command writes:

```text
generated/<project>/
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
    ├── floorplan.svg             # when a matching generator contributes it
    └── model.glb                 # when a matching generator contributes it
```

`index.html` embeds the JSON payload and text assets as a direct-file fallback, so the viewer does not require a server. Binary assets remain distinct: only binary files referenced by `gltf` views are base64-encoded into the HTML. The renderer decodes the embedded value to an `ArrayBuffer` and passes it directly to `GLTFLoader.parse`, avoiding a `file://` fetch. Sibling files remain useful to tools and later generators.

Pinned browser dependencies are copied from Python package resources into `assets/vendor/`. The HTML loads them as classic sibling scripts, not through `fetch()`, dynamic imports or an import map. This avoids local ES-module origin restrictions that differ across browsers and keeps double-click `file://` use as the default workflow.

`model.json` contains objects, relations, supporting tables, validation findings and summary counts. Each object includes its stable `id`, source file and MBSE/project-management area. `viewer.json` describes available views and grouped navigation. The garden-shed generator contributes both `floorplan.svg` and `model.glb`; both render under direct file opening through their separate text and binary embedding paths.

## Viewer manifest schema

The V0.4 schema remains deliberately small:

```json
{
  "schema_version": "0.4",
  "project": "garden_tool_shed",
  "default_view": "overview",
  "views": [
    {
      "id": "floor-plan",
      "title": "Floor Plan",
      "group": "Geometry",
      "type": "svg",
      "source": "views/floorplan.svg",
      "description": "Conceptual 2D layout derived from modeled parts."
    },
    {
      "id": "conceptual-3d",
      "title": "3D",
      "group": "Geometry",
      "type": "gltf",
      "source": "views/model.glb",
      "description": "Conceptual 3D view; not construction-ready."
    }
  ]
}
```

Fields:

- `schema_version` identifies the manifest contract.
- `project` is display/project metadata, not an engineering object identity.
- `default_view` is the initially activated view ID, or `null` for an empty manifest.
- `views` is an ordered list; the viewer derives navigation group and item order from it.
- `id` is a viewer-local view identity.
- `title` and `group` are display/navigation metadata.
- `type` selects a renderer.
- `source` is an optional safe path relative to the bundle root.
- `description` is optional explanatory text.
- `config` is optional renderer-specific configuration. Built-in object views currently use it to select an area.

Generation rejects empty or duplicate view IDs, an undefined `default_view`, missing source fields for asset renderers, and absolute, traversing or otherwise unsafe source paths. Unknown renderer types remain valid so a newer manifest can degrade gracefully in an older viewer.

View IDs do not replace model-object IDs. A view called `architecture` may display `PART-012`, but `PART-012` remains the identity shared with every other representation.

## V0.4 view types

The asset-oriented contract covers at least these types:

| Type | V0.4 behavior | Identity convention |
|---|---|---|
| `mermaid` | Renders generated Mermaid from the local pinned browser asset and always exposes the source text. | Renderer receives the common selected object ID; highlighting is deferred. |
| `graph` | Contract and selection-aware placeholder only; no graph library is included. | Graph nodes should use stable MBSE IDs. |
| `svg` | Sanitizes and inserts embedded SVG as DOM content, maps clicks to shared selection, and highlights every element matching the selected ID. | Meaningful source elements use `data-mbse-id="PART-012"`. |
| `gltf` | Renders an embedded GLB with local Three.js, automatic framing, lighting, orbit/zoom/pan controls, click-only raycast selection and generic highlight restoration. | glTF nodes use `extras.mbse_id`, for example `{"mbse_id": "PART-012"}`. |

The viewer also uses small built-in data renderers: `overview`, `objects`, `tables`, `relations` and `validation`. These preserve the useful viewer capabilities that predate the generic asset-view contract.

An unknown `type` does not stop generation or other views. The browser shows an unsupported-view message for that entry, allowing manifests produced by newer generators to degrade safely in an older viewer.

## Common object selection

The browser owns one state value equivalent to:

```javascript
selectedObjectId = "PART-012"
```

Selecting an object row or an object reference in the relations/details UI calls `setSelectedObject`. The shared details panel then shows that object's attributes and direct relations. The active renderer receives `onSelectionChanged(selectedObjectId)`, and the window emits an `mbse-selection-change` event with the same ID.

The generated page exposes a small integration surface at `window.mbseViewer`:

```javascript
window.mbseViewer.getSelectedObjectId()
window.mbseViewer.setSelectedObject("PART-012")
window.mbseViewer.activateView("traceability")
window.mbseViewer.registerRenderer("custom-type", factory)
```

A renderer factory is called with `(view, context)` and returns any of these lifecycle methods:

```javascript
{
  mount(container) {},
  onSelectionChanged(selectedObjectId) {},
  unmount() {}
}
```

The context supplies the generated model, manifest, embedded text assets, separately encoded GLB assets, and selection getters/setters. Mermaid, graph, SVG and glTF renderers can therefore synchronize selection without moving ownership out of the viewer shell.

## Interactive SVG identity and selection

An SVG shape or group that represents a model object carries the object's existing stable ID:

```xml
<g data-mbse-id="PART-012">
  <!-- generated geometry -->
</g>
```

The SVG renderer does not maintain a second selected value. A click finds the nearest `data-mbse-id` element and calls `context.setSelectedObject(id)`. The viewer validates the ID against `model.json`, updates the common detail panel, and calls the active renderer's `onSelectionChanged`. The renderer then applies `mbse-selected` to all inline SVG elements whose `data-mbse-id` equals that shared value. Clearing or changing selection removes the class from the other elements.

## SVG sanitization boundary

SVG is treated as potentially unsafe generated input. During Python export, the sanitizer parses the SVG as XML, requires an `<svg>` root, rejects document type/entity declarations, removes executable or foreign-content elements, removes inline event attributes and style attributes, and removes external or `javascript:` resource URLs. The sanitized form is written to the sibling `.svg` and embedded in the HTML.

Before insertion, the browser repeats the small allow-by-removal check with `DOMParser` and imports the sanitized SVG node. The renderer never injects the SVG source with `innerHTML`. This is deliberately narrow for generated engineering diagrams: scripts, `foreignObject`, embedded HTML/media, animation elements, inline handlers and external resources are outside the supported SVG profile.

## Interactive glTF identity and selection

A glTF node representing an engineering object carries the existing stable ID in standards-compatible node metadata:

```json
{
  "name": "Right-end shelving unit",
  "extras": {
    "mbse_id": "PART-012"
  }
}
```

`GLTFLoader` preserves node extras in `Object3D.userData`. The renderer records primary `pointerdown`, tracks movement, and raycasts only on `pointerup` when movement remained below 5 pixels. OrbitControls therefore receives the same pointer stream, but an orbit drag does not accidentally select an object. Raycasting starts at the clicked mesh and searches upward for the nearest `userData.mbse_id`, then calls `context.setSelectedObject(id)`. The 3D renderer never owns a second authoritative selection value.

On `onSelectionChanged(id)`, every descendant mesh whose nearest mapped ancestor has that ID receives a cloned highlight material. Before another selection or unmount, the renderer disposes those clones and restores the exact original material references.

Every renderer must treat `unmount()` as final for that instance. The glTF renderer marks itself disposed before cleanup, cancels its animation frame, disconnects its `ResizeObserver`, removes all pointer listeners, disposes OrbitControls, geometries, materials, textures, helper resources and the WebGL renderer, then explicitly releases the context. If `GLTFLoader.parse()` completes after unmount, the newly returned scenes are traversed and disposed without being attached. Cleanup is idempotent enough for normal errors and repeated `3D → SVG → 3D → Requirements → 3D` cycles.

## Offline browser dependencies and direct-file behavior

The viewer packages Three.js `0.180.0` and Mermaid `11.17.2`. `application/tools/viewer-assets/package-lock.json` pins those packages and esbuild `0.25.9`. The Three.js updater bundles core, `GLTFLoader` and `OrbitControls` into one classic script; Mermaid's published classic browser build is copied unchanged. Both live under `mbse_lite/_vendor/viewer` as Python package resources. `export_viewer` integrity-checks them against SHA-256 values in the packaged manifest and copies them into `assets/vendor/`.

To update intentionally:

```bash
cd application/tools/viewer-assets
npm ci
npm run build
```

Node is an asset-maintenance tool only; normal Python installation, tests and viewer generation do not invoke it. Classic sibling scripts were chosen because browser handling of local ES-module imports is inconsistent under `file://`. The viewer contains no CDN reference for these core dependencies. If a script is missing or fails to initialize, only its Mermaid or 3D view reports the problem. Mermaid render errors and malformed GLB data are likewise caught within the affected renderer. Invalid or unsafe SVG is omitted during export and recorded as a localized per-view asset error instead of being written or aborting unrelated views.

Three.js and Mermaid are MIT-licensed. Their license files are package resources and are copied into each generated bundle. An update must preserve upstream notices and review any changed license obligations, including code bundled transitively by Mermaid.

## Adding generated views

Application or domain generators can call `export_viewer` with `ViewDefinition` entries and a `view_assets` mapping. A generator may supply text or binary assets through `Mapping[str, str | bytes]` without changing the generic viewer's project logic. Every asset path passes the same bundle-relative path validation before text or bytes are written. Unreferenced binary assets are written as sibling files but are not needlessly embedded in HTML.

Default export also runs the small registry in `mbse_lite.visualization`. A domain generator contributes views only when the project explicitly opts into its visualization profile. Project-specific code generates a representation from authoritative project data, attaches stable MBSE IDs, and describes it in the manifest. It does not encode project facts in `viewer.py`, nor promote the generated asset to an authoritative model.

## Visualization profile and role mapping

A visualization profile is a reserved Markdown table with this shape:

```markdown
| Visualization Profile | Role | Object ID | Expected Type |
|---|---|---|---|
| garden_shed | enclosure | PART-001 | Part |
| garden_shed | shelving | PART-012 | Part |
```

The table is project-specific visualization metadata. It maps a generator's semantic role to an existing stable MBSE ID; it does not repeat the object's name, description, requirements or geometry and is not an alternative engineering model. Profile and role names use lower-case letters, digits and underscores. A referenced ID must exist and match `Expected Type`; a registered generator may additionally require a fixed role set and type for each role. Duplicate roles, missing IDs, incompatible types and missing required roles fail viewer generation and CLI validation clearly.

Projects without a recognized profile remain generic. In particular, `demo_project` does not activate the garden-shed generator merely because it happens to contain parts with similar names.

## Garden-shed shared conceptual visualization

The garden-shed generator resolves its seven required part roles from `projects/garden_tool_shed/visualization.md`. Renaming a mapped object does not affect activation or role resolution because identity comes only from the mapped ID. Current preferred candidate annotations are derived generically from `Concept` objects whose status is `Preferred candidate`, without exact name matching.

Both SVG and GLB consume one small internal `GardenShedVisualizationSpec`; they do not maintain unrelated coordinate assumptions. The approximate footprint stated by the project requirement sets the envelope proportions. The current unresolved display defaults are: 2.2 m height, 0.06 m wall thickness, 0.08 m floor thickness, 1.85 m door height, 0.8 m ramp length, 22% of length for the mower zone and 11% for the shelving allocation. Door offsets, widths and other internal placements are normalized presentation choices.

Those values are visualization state only. They are neither written back to Markdown nor authoritative engineering dimensions. The generator records them and the displayed preferred candidate IDs in view config. Both views identify themselves as conceptual and not construction-ready.

The deterministic GLB writer has no added Python dependency. It writes glTF 2.0 box primitives, materials, transforms and node metadata into one binary asset. It is deliberately a conceptual exchange/view generator, not a CAD kernel.

## Intentionally deferred

V0.4 does not include an interactive graph library, two-way Mermaid synchronization, graphical editing, browser-to-Markdown writes, detailed CAD, construction geometry or parametric modeling. The intended future boundary is:

```text
Markdown MBSE
     ↓
role/profile mapping
     ↓
geometry specification
     ↓
CadQuery or another domain generator
     ↓
SVG / GLB / STEP
     ↓
Web viewer
```

CadQuery is not implemented in V0.4. A V0.5 geometry generator can replace or augment the simple box-based GLB writer without changing the viewer, stable-ID or shared-selection contracts.
