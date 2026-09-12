# View Architecture V0.3

## Purpose

A **View** is one representation of the shared MBSE Lite model. A view does not own engineering identity or become a second model: it references objects through the same stable IDs used in the authoritative Markdown.

View Architecture V0.3 separates three concerns:

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
└── views/
    ├── traceability.mmd
    ├── delivery-traceability.mmd
    ├── floorplan.svg             # when a matching generator contributes it
    └── model.glb                 # when a matching generator contributes it
```

`index.html` embeds the JSON payload and text assets as a direct-file fallback, so the viewer does not require a server. Binary assets remain distinct: only binary files referenced by `gltf` views are base64-encoded into the HTML. The renderer decodes the embedded value to an `ArrayBuffer` and passes it directly to `GLTFLoader.parse`, avoiding a `file://` fetch. Sibling files remain useful to tools and later generators.

`model.json` contains objects, relations, supporting tables, validation findings and summary counts. Each object includes its stable `id`, source file and MBSE/project-management area. `viewer.json` describes available views and grouped navigation. The garden-shed generator contributes both `floorplan.svg` and `model.glb`; both render under direct file opening through their separate text and binary embedding paths.

## Viewer manifest schema

The V0.3 schema is deliberately small:

```json
{
  "schema_version": "0.3",
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

## V0.3 view types

The asset-oriented contract covers at least these types:

| Type | V0.3 behavior | Identity convention |
|---|---|---|
| `mermaid` | Renders generated Mermaid when the CDN module is available and always exposes the source text. | Renderer receives the common selected object ID; highlighting is deferred. |
| `graph` | Contract and selection-aware placeholder only; no graph library is included. | Graph nodes should use stable MBSE IDs. |
| `svg` | Sanitizes and inserts embedded SVG as DOM content, maps clicks to shared selection, and highlights every element matching the selected ID. | Meaningful source elements use `data-mbse-id="PART-012"`. |
| `gltf` | Renders an embedded GLB with Three.js, automatic framing, lighting, orbit/zoom/pan controls, raycast selection and generic highlight restoration. | glTF nodes use `extras.mbse_id`, for example `{"mbse_id": "PART-012"}`. |

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

`GLTFLoader` preserves node extras in `Object3D.userData`. Raycasting starts at the clicked mesh and searches upward for the nearest `userData.mbse_id`, then calls `context.setSelectedObject(id)`. The 3D renderer never owns a second authoritative selection value.

On `onSelectionChanged(id)`, every descendant mesh whose nearest mapped ancestor has that ID receives a cloned highlight material. Before another selection or unmount, the renderer disposes those clones and restores the exact original material references. Unmount also removes pointer and resize observers, cancels rendering, disposes controls, model resources and the WebGL renderer, and releases the context.

## Three.js loading and direct-file behavior

The generated page uses an import map pinned to Three.js r180 on jsDelivr. Core Three.js, `GLTFLoader` and `OrbitControls` come from that same version and CDN. The 3D renderer uses the base64-embedded GLB rather than fetching `views/model.glb`, so binary transport itself works under `file://`.

Three.js still requires network access in V0.3. Its dynamic import is isolated behind a promise that resolves to `null` on failure. In that case the 3D host shows a dependency message; the viewer shell, object/detail views, SVG and locally embedded data remain usable. Bundling pinned Three.js modules for fully offline rendering is a desirable future extension.

## Adding generated views

Application or domain generators can call `export_viewer` with `ViewDefinition` entries and a `view_assets` mapping. A generator may supply text or binary assets through `Mapping[str, str | bytes]` without changing the generic viewer's project logic. Every asset path passes the same bundle-relative path validation before text or bytes are written. Unreferenced binary assets are written as sibling files but are not needlessly embedded in HTML.

Default export also runs the small registry in `mbse_lite.visualization`. A domain generator inspects the parsed model and contributes views only when its required modeled roles are present. Project-specific code generates a representation from authoritative project data, attaches stable MBSE IDs, and describes it in the manifest. It does not encode project facts in `viewer.py`, nor promote the generated asset to an authoritative model.

## Garden-shed shared conceptual visualization

The garden-shed generator recognizes the modeled parts by their parsed `Part` names and uses their actual IDs. Name-based role detection remains isolated so it can later be replaced by an explicit visualization profile/role mapping. It represents the storage enclosure (`PART-001`), main storage zone (`PART-004`), enclosed mower compartment (`PART-005`), double-leaf main door (`PART-008`), mower external door (`PART-010`), mower ramp (`PART-011`) and right-end shelving (`PART-012`).

Both SVG and GLB consume one small internal `GardenShedVisualizationSpec`; they do not maintain unrelated coordinate assumptions. The approximate footprint stated by the project requirement sets the envelope proportions. The current unresolved display defaults are: 2.2 m height, 0.06 m wall thickness, 0.08 m floor thickness, 1.85 m door height, 0.8 m ramp length, 22% of length for the mower zone and 11% for the shelving allocation. Door offsets, widths and other internal placements are normalized presentation choices.

Those values are visualization state only. They are neither written back to Markdown nor authoritative engineering dimensions. The generator records them and the displayed preferred candidate IDs in view config. Both views identify themselves as conceptual and not construction-ready.

The deterministic GLB writer has no added Python dependency. It writes glTF 2.0 box primitives, materials, transforms and node metadata into one binary asset. It is deliberately a conceptual exchange/view generator, not a CAD kernel.

## Intentionally deferred

V0.3 does not include an interactive graph library, two-way Mermaid synchronization, graphical editing, browser-to-Markdown writes, detailed CAD, construction geometry or parametric modeling. A future version can add an explicit visualization profile and then introduce a separate CAD-authoritative/parametric pipeline without changing the stable-ID or shared-selection contracts proved here.
