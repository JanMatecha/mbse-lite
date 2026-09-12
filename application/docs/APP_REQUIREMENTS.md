# MBSE Lite Application Requirements

Application requirements are intentionally separated from the engineering requirements of projects under `../projects/`.

| ID | Requirement | Status |
|---|---|---|
| APP-REQ-001 | The application shall treat project Markdown files as the authoritative project model. | Implemented |
| APP-REQ-002 | The application shall detect duplicate model object IDs. | Implemented |
| APP-REQ-003 | The application shall validate relation source and target references. | Implemented |
| APP-REQ-004 | The application shall provide basic requirement traceability checks. | Implemented |
| APP-REQ-005 | The application shall generate Mermaid traceability output. | Implemented |
| APP-REQ-006 | The application shall generate a static HTML project overview. | Implemented |
| APP-REQ-007 | The application shall export project data to a LibreOffice-compatible XLSX workbook. | Implemented |
| APP-REQ-008 | XLSX import shall create reviewable Markdown output and shall not silently overwrite the authoritative project model. | Implemented |
| APP-REQ-009 | The application shall remain usable without a database or continuously running server in the POC phase. | Implemented |
| APP-REQ-010 | The application model shall remain reasonably mappable to SysML v2 concepts in future versions. | Guiding |
| APP-REQ-011 | The application shall provide a local read-only interactive web viewer that can be generated from a project and opened directly in a browser without a continuously running application server. | Implemented |
| APP-REQ-012 | The application shall support physically separated MBSE and project-management Markdown areas within one project while preserving explicit relations across those areas. | Implemented |
| APP-REQ-013 | The local viewer shall present MBSE objects separately from project-management objects while retaining visibility of cross-area relations. | Implemented |
| APP-REQ-014 | The local viewer shall expose supporting project Markdown tables that are not model objects or relation tables. | Implemented |
| APP-REQ-015 | The local viewer shall derive grouped navigation and renderer selection from a generated project-independent view manifest. | Implemented |
| APP-REQ-016 | The local viewer shall maintain one selected stable model-object ID and expose selection changes to the active view renderer. | Implemented |
| APP-REQ-017 | View Architecture V0.1 shall define renderer contracts for Mermaid, graph, SVG and glTF views and shall keep the viewer usable when a view type is unsupported. | Implemented |
| APP-REQ-018 | The local viewer shall render generated SVG as interactive DOM content and synchronize SVG clicks and highlights through the viewer's one selected stable model-object ID. | Implemented |
| APP-REQ-019 | The application shall sanitize generated SVG before embedding or DOM insertion by removing executable content, inline event handlers and unsafe external resource references. | Implemented |
| APP-REQ-020 | Domain visualization generators shall derive identity and available engineering facts from the parsed Markdown model and shall identify visualization-only geometry as non-authoritative. | Implemented |
| APP-REQ-021 | Visualization generators and viewer export shall support safe bundle-relative text and binary assets without allowing asset paths to escape the generated output directory. | Implemented |
| APP-REQ-022 | The local viewer shall render generated glTF/GLB engineering views with orbit, zoom, pan and automatic model framing when the pinned Three.js modules are available. | Implemented |
| APP-REQ-023 | Interactive 3D objects shall use existing stable model IDs through `node.extras.mbse_id` and shall synchronize picking and highlighting through the viewer-owned selected object ID. | Implemented |
| APP-REQ-024 | Generated GLB data required for direct `file://` viewing shall be safely encoded in the HTML bundle and parsed without fetching the sibling GLB file. | Implemented |
| APP-REQ-025 | Failure to load the optional browser-side 3D dependency shall remain local to the 3D view and shall not prevent access to other viewer views. | Implemented |
| APP-REQ-026 | Generated viewer bundles shall include pinned local Mermaid and Three.js browser dependencies so core views work without a network connection when opened directly from disk. | Implemented |
| APP-REQ-027 | A project may define visualization-specific Markdown role mappings from semantic roles to existing stable model IDs, and invalid IDs or incompatible object types shall fail validation clearly. | Implemented |
| APP-REQ-028 | An unmounted 3D renderer shall release animation, observer, event, controls, scene and WebGL resources, including glTF scenes that finish loading after unmount. | Implemented |
| APP-REQ-029 | Three-dimensional selection shall occur for a short pointer click and shall not be triggered by a meaningful orbit-drag movement. | Implemented |

## Rule for adding requirements

Add an `APP-REQ-*` only for a reusable toolkit capability or constraint. Do not add a one-project technical requirement here.
