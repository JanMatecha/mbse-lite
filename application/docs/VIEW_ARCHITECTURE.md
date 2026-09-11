# View Architecture V0.1

## Purpose

A **View** is one representation of the shared MBSE Lite model. A view does not own engineering identity or become a second model: it references objects through the same stable IDs used in the authoritative Markdown.

View Architecture V0.1 separates three concerns:

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
    └── delivery-traceability.mmd
```

`index.html` embeds the JSON payload and text assets as a direct-file fallback, so the viewer does not require a server. The sibling files remain useful to tools and later generators.

`model.json` contains objects, relations, supporting tables, validation findings and summary counts. Each object includes its stable `id`, source file and MBSE/project-management area. `viewer.json` describes available views and grouped navigation.

## Viewer manifest schema

The V0.1 schema is deliberately small:

```json
{
  "schema_version": "0.1",
  "project": "garden_tool_shed",
  "default_view": "overview",
  "views": [
    {
      "id": "traceability",
      "title": "Traceability",
      "group": "System",
      "type": "mermaid",
      "source": "views/traceability.mmd",
      "description": "Engineering-object traceability generated from explicit relations."
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

View IDs do not replace model-object IDs. A view called `architecture` may display `PART-012`, but `PART-012` remains the identity shared with every other representation.

## V0.1 view types

The asset-oriented contract covers at least these types:

| Type | V0.1 behavior | Identity convention |
|---|---|---|
| `mermaid` | Renders generated Mermaid when the CDN module is available and always exposes the source text. | Renderer receives the common selected object ID; highlighting is deferred. |
| `graph` | Contract and selection-aware placeholder only; no graph library is included. | Graph nodes should use stable MBSE IDs. |
| `svg` | Displays a safe relative SVG asset through an image element. | Source elements should use `data-mbse-id="PART-012"`; interactive selection/highlighting is deferred. |
| `gltf` | Contract and selection-aware placeholder only; no WebGL library is included. | glTF nodes should use `extras.mbse_id`, for example `{"mbse_id": "PART-012"}`. |

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

The context supplies the generated model, manifest, embedded text assets, and selection getters/setters. Later Mermaid, interactive graph, SVG and glTF renderers can therefore synchronize selection without moving ownership out of the viewer shell.

## Adding generated views

Application or domain generators can call `export_viewer` with `ViewDefinition` entries and a `view_assets` mapping. Asset paths must be relative to the output bundle; traversal and absolute paths are rejected. A generator may supply text or binary assets without changing the generic viewer's project logic.

Project-specific code should generate a representation from authoritative project data, attach stable MBSE IDs, and describe it in the manifest. It must not encode project facts in `viewer.py`, nor promote the generated asset to an authoritative model.

## Intentionally deferred

V0.1 does not include an interactive graph library, Three.js, full two-way Mermaid/SVG/glTF synchronization, graphical editing, browser-to-Markdown writes or parametric geometry generation. Those capabilities can be added behind the existing view and selection contracts.
