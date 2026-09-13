from __future__ import annotations

import base64
import json
import re
from html import escape
from pathlib import Path
from typing import Mapping, Sequence
from xml.etree import ElementTree

from .browser_assets import (
    MERMAID_ASSET_PATH,
    THREE_ASSET_PATH,
    browser_dependency_assets,
)
from .core import Model
from .view_architecture import (
    ViewDefinition,
    build_default_view_assets,
    build_viewer_manifest,
    build_viewer_model,
    default_view_definitions,
    is_safe_view_source,
)
from .visualization import build_generated_views


_BLOCKED_SVG_ELEMENTS = frozenset(
    {
        "script",
        "foreignobject",
        "style",
        "iframe",
        "object",
        "embed",
        "link",
        "meta",
        "audio",
        "video",
        "image",
        "animate",
        "animatemotion",
        "animatetransform",
        "set",
        "discard",
    }
)
_SVG_URI_ATTRIBUTES = frozenset({"href", "src"})


def _json_for_html(value: object) -> str:
    """Serialize data for a script block without allowing an early script close."""

    return (
        json.dumps(value, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _asset_output_path(output_dir: Path, source: str) -> Path:
    if not is_safe_view_source(source):
        raise ValueError(f"View asset path must be a safe relative path: {source!r}")
    return output_dir.joinpath(*source.replace("\\", "/").split("/"))


def _xml_local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def _unsafe_svg_attribute(name: str, value: str) -> bool:
    local_name = _xml_local_name(name)
    compact_value = re.sub(r"\s+", "", value).lower()
    if local_name == "style" or local_name.startswith("on"):
        return True
    if "javascript:" in compact_value:
        return True
    if local_name in _SVG_URI_ATTRIBUTES and value.strip() and not value.strip().startswith("#"):
        return True
    if re.search(r"url\s*\(", value, re.IGNORECASE) and not re.fullmatch(
        r"\s*url\(\s*#[A-Za-z_][\w.-]*\s*\)\s*", value
    ):
        return True
    return False


def _sanitize_svg(source: str) -> str:
    """Remove executable and externally loaded SVG constructs before export."""

    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", source, re.IGNORECASE):
        raise ValueError("SVG document type and entity declarations are not allowed")
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError as error:
        raise ValueError(f"Invalid SVG content: {error}") from error
    if _xml_local_name(root.tag) != "svg":
        raise ValueError("SVG view assets must have an <svg> root element")

    def clean(element: ElementTree.Element) -> None:
        for attribute, value in list(element.attrib.items()):
            if _unsafe_svg_attribute(attribute, value):
                del element.attrib[attribute]
        for child in list(element):
            if _xml_local_name(child.tag) in _BLOCKED_SVG_ELEMENTS:
                element.remove(child)
            else:
                clean(child)

    clean(root)
    ElementTree.register_namespace("", "http://www.w3.org/2000/svg")
    ElementTree.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    return ElementTree.tostring(root, encoding="unicode", short_empty_elements=True) + "\n"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_viewer(
    model: Model,
    output: str | Path,
    *,
    project_name: str = "MBSE Lite Project",
    views: Sequence[ViewDefinition] | None = None,
    view_assets: Mapping[str, str | bytes] | None = None,
    cad_preview_dir: str | Path | None = None,
    data_provider: str = "embedded",
) -> None:
    """Generate manifest-driven viewer HTML and its local browser assets.

    ``output`` remains the HTML path for backwards compatibility. Embedded
    mode is the default read-only ``file://`` bundle. HTTP mode emits the same
    renderer with its project data supplied by the local server. The bundle
    also contains sibling ``model.json``, ``viewer.json`` and referenced view
    assets. Text assets and selected binary renderer assets are embedded in the
    HTML so the viewer still works when opened directly through ``file://``.
    """

    if data_provider not in {"embedded", "http"}:
        raise ValueError(f"Unsupported viewer data provider: {data_provider}")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    assets: dict[str, str | bytes] = {}
    if views is None:
        definitions = list(default_view_definitions())
        assets.update(build_default_view_assets(model))
        generated = build_generated_views(model)
        definitions.extend(generated.views)
        assets.update(generated.assets)
        if cad_preview_dir is not None:
            from .cad.preview import validate_cad_preview
            from .cad.protocol import CAD_COMPONENT_ROLES
            from .visualization import (
                GARDEN_SHED_PROFILE,
                GARDEN_SHED_REQUIRED_ROLES,
                resolve_visualization_profile,
            )

            roles = resolve_visualization_profile(
                model, GARDEN_SHED_PROFILE, GARDEN_SHED_REQUIRED_ROLES
            )
            if roles is None:
                raise ValueError(
                    "CAD preview requires the project's conceptual-3d generated view"
                )
            expected_component_ids = tuple(
                roles[role].id for role in CAD_COMPONENT_ROLES
            )

            preview = validate_cad_preview(
                cad_preview_dir,
                model_object_ids=set(model.objects),
                expected_component_ids=expected_component_ids,
            )
            replacement = ViewDefinition(
                id="conceptual-3d",
                title="3D",
                group="Geometry",
                type="gltf",
                source="views/conceptual-preview.glb",
                description=(
                    "Conceptual CAD preview generated from the model. It is for "
                    "visualization only and is not construction-ready."
                ),
                config={
                    "geometry_status": "conceptual",
                    "asset_role": "conceptual-cad-preview",
                    "authority": "visualization-only",
                    "source_unit": preview.source_unit,
                    "viewer_scale": preview.viewer_scale,
                    "identity_contract": "extras.mbse_id",
                    "notice": "Conceptual CAD preview — visualization only",
                },
            )
            replaced = False
            for index, definition in enumerate(definitions):
                if definition.id == "conceptual-3d":
                    definitions[index] = replacement
                    replaced = True
                    break
            if not replaced:
                raise ValueError(
                    "CAD preview requires the project's conceptual-3d generated view"
                )
            assets.pop("views/model.glb", None)
            assets["views/conceptual-preview.glb"] = preview.data
    else:
        definitions = list(views)
    if view_assets:
        assets.update(view_assets)
    dependency_assets = browser_dependency_assets()
    dependency_collisions = sorted(set(assets).intersection(dependency_assets))
    if dependency_collisions:
        raise ValueError(
            "View assets collide with packaged browser dependencies: "
            + ", ".join(dependency_collisions)
        )
    assets.update(dependency_assets)

    viewer_model = build_viewer_model(model)
    manifest = build_viewer_manifest(project_name, definitions)
    asset_errors: dict[str, str] = {}
    svg_sources = {
        view.source for view in definitions if view.type == "svg" and view.source is not None
    }
    for source in svg_sources.intersection(set(assets)):
        content = assets[source]
        if not isinstance(content, str):
            asset_errors[source] = f"SVG view asset must be UTF-8 text: {source}"
            del assets[source]
            continue
        try:
            assets[source] = _sanitize_svg(content)
        except ValueError as error:
            asset_errors[source] = f"SVG asset is invalid or unsafe: {error}"
            del assets[source]

    _write_json(output_path.parent / "model.json", viewer_model)
    _write_json(output_path.parent / "viewer.json", manifest)

    for source, content in assets.items():
        asset_path = _asset_output_path(output_path.parent, source)
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            asset_path.write_bytes(content)
        else:
            asset_path.write_text(content, encoding="utf-8")

    embedded_assets = {
        source: content for source, content in assets.items() if isinstance(content, str)
    }
    gltf_sources = {
        view.source
        for view in definitions
        if view.type == "gltf" and view.source is not None
    }
    embedded_binary_assets = {
        source: base64.b64encode(content).decode("ascii")
        for source, content in assets.items()
        if isinstance(content, bytes) and source in gltf_sources
    }
    title = escape(project_name)

    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · MBSE Lite Viewer</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #f6f7f9;
  --panel: #ffffff;
  --text: #172033;
  --muted: #667085;
  --line: #d9dee8;
  --accent: #2457d6;
  --accent-soft: #e9efff;
  --ok: #147a45;
  --warn: #9a6700;
  --error: #b42318;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #11151d;
    --panel: #191f2a;
    --text: #eef2f8;
    --muted: #a8b0bf;
    --line: #354052;
    --accent: #84a8ff;
    --accent-soft: #263554;
    --ok: #6ce9a6;
    --warn: #fdb022;
    --error: #f97066;
  }
}
* { box-sizing: border-box; }
body { margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
header { position: sticky; top: 0; z-index: 10; display: flex; gap: 1rem; align-items: center; justify-content: space-between; padding: 1rem 1.4rem; background: var(--panel); border-bottom: 1px solid var(--line); }
.brand h1 { margin: 0; font-size: 1.15rem; }
.brand p { margin: .2rem 0 0; color: var(--muted); font-size: .85rem; }
.layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); height: calc(100vh - 74px); min-height: 620px; }
nav { padding: 1rem; border-right: 1px solid var(--line); background: var(--panel); overflow-y: auto; }
.nav-group { margin: 0 0 1rem; }
.nav-group h2 { margin: 0 0 .35rem; padding: 0 .8rem; color: var(--muted); font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; }
nav button { width: 100%; border: 0; background: transparent; color: var(--text); text-align: left; padding: .62rem .8rem; margin-bottom: .12rem; border-radius: .5rem; cursor: pointer; font: inherit; }
nav button:hover, nav button.active { background: var(--accent-soft); color: var(--accent); }
main.workspace { display: grid; grid-template-rows: minmax(280px, 43%) minmax(0, 57%); min-width: 0; min-height: 0; overflow: hidden; }
.workspace-upper { min-width: 0; min-height: 0; padding: 1.4rem; overflow: auto; }
.selected-object-panel { min-width: 0; min-height: 0; padding: 1.2rem 1.4rem 1.5rem; overflow: auto; background: var(--panel); border-top: 1px solid var(--line); }
h2 { margin-top: 0; }
h3 { margin-top: 1.4rem; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .8rem; margin: 1rem 0 1.5rem; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; padding: 1rem; }
.card strong { display: block; font-size: 1.65rem; margin-top: .25rem; }
.muted { color: var(--muted); }
.toolbar { display: flex; gap: .65rem; flex-wrap: wrap; margin: .8rem 0 1rem; }
input, select, textarea { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: .5rem; padding: .55rem .7rem; font: inherit; }
input[type="search"] { min-width: min(420px, 100%); flex: 1; }
.primary-action { border: 1px solid var(--accent); border-radius: .5rem; padding: .55rem .8rem; background: var(--accent); color: white; cursor: pointer; font: inherit; }
.primary-action:disabled { cursor: not-allowed; opacity: .55; }
.authoring-actions { display: flex; align-items: center; gap: .75rem; }
.requirement-dialog { width: min(620px, calc(100vw - 2rem)); max-height: calc(100vh - 2rem); overflow: auto; border: 1px solid var(--line); border-radius: .75rem; background: var(--panel); color: var(--text); padding: 1.2rem; }
.requirement-dialog::backdrop { background: rgb(0 0 0 / .45); }
.requirement-dialog h2 { margin: 0 0 .35rem; }
.requirement-form-fields { display: grid; gap: .8rem; margin: 1rem 0; }
.requirement-field { display: grid; gap: .3rem; }
.requirement-field textarea { min-height: 6rem; resize: vertical; }
.dialog-actions { display: flex; justify-content: flex-end; gap: .6rem; }
.dialog-actions button { border: 1px solid var(--line); border-radius: .5rem; padding: .55rem .8rem; background: var(--panel); color: var(--text); cursor: pointer; font: inherit; }
.dialog-actions button[type="submit"] { background: var(--accent); border-color: var(--accent); color: white; }
.creation-feedback { min-height: 1.3rem; margin: .65rem 0 0; }
.creation-feedback.error { color: var(--error); }
.table-wrap { overflow: auto; background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; margin-bottom: 1rem; }
table { border-collapse: collapse; width: 100%; font-size: .92rem; }
th, td { padding: .6rem .75rem; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { position: sticky; top: 0; background: var(--panel); color: var(--muted); font-weight: 600; }
tbody tr:hover, tbody tr.selected { background: var(--accent-soft); }
tbody tr.object-row { cursor: pointer; }
.badge { display: inline-block; border: 1px solid var(--line); border-radius: 99px; padding: .12rem .5rem; font-size: .78rem; white-space: nowrap; }
.severity-ERROR { color: var(--error); font-weight: 700; }
.severity-WARNING { color: var(--warn); font-weight: 700; }
.severity-OK { color: var(--ok); font-weight: 700; }
.selected-object-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: .85rem; }
.selected-object-heading { display: flex; align-items: center; gap: .65rem; flex-wrap: wrap; }
.selected-object-heading h2 { margin: 0; font-size: 1.08rem; }
.selected-object-actions { display: flex; gap: .55rem; }
.secondary-action { border: 1px solid var(--line); border-radius: .5rem; padding: .5rem .8rem; background: var(--panel); color: var(--text); cursor: pointer; font: inherit; }
.detail-tabs { display: flex; gap: .2rem; border-bottom: 1px solid var(--line); margin-bottom: 1rem; }
.detail-tab { border: 0; border-bottom: 2px solid transparent; padding: .55rem .8rem; background: transparent; color: var(--muted); cursor: pointer; font: inherit; }
.detail-tab.active { border-bottom-color: var(--accent); color: var(--accent); font-weight: 600; }
.object-metadata { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .75rem 1rem; margin: 0 0 1.2rem; }
.object-metadata div { min-width: 0; }
.object-metadata dt { margin-bottom: .2rem; color: var(--muted); font-size: .76rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
.object-metadata dd { margin: 0; overflow-wrap: anywhere; }
.attribute-list { display: grid; gap: 1rem; }
.attribute-block { min-width: 0; }
.attribute-block h3 { margin: 0 0 .35rem; color: var(--muted); font-size: .82rem; font-weight: 600; letter-spacing: .035em; text-transform: uppercase; }
.attribute-value { width: 100%; padding: .7rem .8rem; border: 1px solid var(--line); border-radius: .55rem; background: var(--bg); white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.5; }
.attribute-value.long-text { min-height: 4.8rem; }
.attribute-editor { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: .5rem; align-items: start; }
.attribute-editor input, .attribute-editor textarea { min-width: 0; width: 100%; }
.attribute-editor textarea { min-height: 7.5rem; resize: vertical; line-height: 1.45; }
.attribute-editor button { border: 1px solid var(--accent); border-radius: .45rem; padding: .55rem .75rem; background: var(--accent); color: white; cursor: pointer; }
.attribute-editor button:disabled { cursor: wait; opacity: .65; }
.edit-feedback { margin: 0 0 1rem; padding: .55rem .65rem; border-radius: .45rem; background: var(--accent-soft); }
.edit-feedback.error { color: var(--error); }
.detail-relations { padding-left: 1.2rem; }
.detail-relations li { margin: .65rem 0; overflow-wrap: anywhere; }
.graph { background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; padding: 1rem; overflow: auto; margin-bottom: 1rem; }
.data-block { margin: 1rem 0 1.4rem; }
.data-block h3 { margin-bottom: .35rem; }
.scaffold { border: 1px dashed var(--line); border-radius: .7rem; padding: 1.2rem; background: var(--panel); }
.engineering-asset { display: block; width: 100%; max-height: 70vh; object-fit: contain; border: 1px solid var(--line); background: white; }
.svg-host { overflow: auto; }
.svg-host svg { display: block; width: 100%; max-height: 72vh; background: white; }
.svg-host svg [data-mbse-id] { cursor: pointer; transition: filter .12s ease, opacity .12s ease; }
.svg-host svg [data-mbse-id]:hover { filter: brightness(.96) drop-shadow(0 0 3px var(--accent)); }
.svg-host svg [data-mbse-id].mbse-selected { filter: drop-shadow(0 0 7px var(--accent)); }
.svg-host svg [data-mbse-id].mbse-selected:is(rect, path, line, circle, ellipse, polygon, polyline),
.svg-host svg [data-mbse-id].mbse-selected > :is(rect, path, line, circle, ellipse, polygon, polyline) { stroke: var(--accent) !important; stroke-width: 8px !important; }
.gltf-host { position: relative; min-height: 440px; height: min(72vh, 680px); padding: 0; overflow: hidden; background: #eef1f5; }
.gltf-host canvas { display: block; width: 100%; height: 100%; cursor: grab; }
.gltf-host canvas:active { cursor: grabbing; }
.gltf-status { position: absolute; inset: auto 1rem 1rem 1rem; margin: 0; padding: .65rem .8rem; border-radius: .5rem; background: color-mix(in srgb, var(--panel) 90%, transparent); color: var(--muted); pointer-events: none; }
.gltf-notice { position: absolute; inset: 1rem auto auto 1rem; z-index: 1; margin: 0; padding: .45rem .65rem; border-radius: .5rem; background: color-mix(in srgb, var(--panel) 92%, transparent); color: var(--muted); font-size: .82rem; pointer-events: none; }
.link-button { border: 0; padding: 0; background: transparent; color: var(--accent); cursor: pointer; font: inherit; font-weight: 600; }
details { margin-top: 1rem; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 1050px) {
  .layout { grid-template-columns: 210px minmax(0, 1fr); }
  .object-metadata { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .layout { grid-template-columns: 1fr; height: auto; min-height: 0; }
  nav { display: flex; gap: .6rem; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  .nav-group { display: flex; gap: .2rem; margin: 0; }
  .nav-group h2 { align-self: center; white-space: nowrap; }
  nav button { width: auto; white-space: nowrap; }
  main.workspace { display: block; overflow: visible; }
  .workspace-upper, .selected-object-panel { overflow: visible; }
  .workspace-upper { min-height: 360px; }
  .object-metadata { grid-template-columns: 1fr; }
  .attribute-editor { grid-template-columns: 1fr; }
  .attribute-editor button { justify-self: start; }
}
</style>
<script src="__THREE_ASSET_PATH__"></script>
<script src="__MERMAID_ASSET_PATH__"></script>
<script>
window.mbseThreeReady = Promise.resolve(window.mbseThreeModules || null);
window.mbseMermaidReady = Promise.resolve().then(() => {
  const mermaid = window.mermaid;
  if (!mermaid?.initialize) {
    console.info('The local Mermaid dependency is unavailable. Source remains available.');
    return null;
  }
  try {
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
    return mermaid;
  } catch (error) {
    console.info('Mermaid could not be initialized. Source remains available.', error);
    return null;
  }
});
</script>
</head>
<body>
<header>
  <div class="brand">
    <h1>__TITLE__</h1>
    <p>__MODE_LABEL__</p>
  </div>
  <div class="authoring-actions"><div id="modelCounts" class="muted"></div>__AUTHORING_UI__</div>
</header>
<div class="layout">
  <nav id="viewNavigation" aria-label="Project views"></nav>
  <main class="workspace">
    <section class="workspace-upper" aria-label="Active project view"><div id="viewContent"></div></section>
    <section id="selectedObjectPanel" class="selected-object-panel" aria-label="Selected object">
      <div id="objectDetail" class="detail muted">Select an object to inspect its attributes and direct relations.</div>
    </section>
  </main>
</div>
<script>
__PROVIDER_SOURCE__
__AUTHORING_SOURCE__

let viewerManifest = null;
let viewerModel = null;
let objects = [];
let relations = [];
let supportingTables = [];
let findings = [];

const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

const viewHeader = (view) => `
  <h2>${escapeHtml(view.title)}</h2>
  ${view.description ? `<p class="muted">${escapeHtml(view.description)}</p>` : ''}`;

let selectedObjectId = null;
let activeViewId = null;
let activeRenderer = null;
let objectEditFeedback = null;
let selectedObjectMode = 'read';
let selectedObjectTab = 'details';

const LONG_TEXT_ATTRIBUTE_NAMES = new Set([
  'concept', 'requirement', 'decision', 'description', 'notes', 'note',
  'issue', 'risk', 'rationale', 'justification', 'assumption', 'comment', 'summary'
]);

function isLongTextAttribute(name, value) {
  const normalizedName = String(name).trim().toLowerCase().replaceAll('_', ' ').replaceAll('-', ' ');
  return String(value ?? '').includes('\\n') || String(value ?? '').length >= 80 ||
    [...LONG_TEXT_ATTRIBUTE_NAMES].some(candidate =>
      normalizedName === candidate || normalizedName.endsWith(` ${candidate}`));
}

function editableAttributesFor(object) {
  if (!dataProvider.capabilities.write) return [];
  return Object.keys(object.attributes).filter(key => object.editable_attributes?.includes(key));
}

function hasUnsavedObjectEdits() {
  if (selectedObjectMode !== 'edit') return false;
  return [...document.querySelectorAll('#objectDetail .attribute-editor [data-original-value]')]
    .some(input => input.value !== input.dataset.originalValue);
}

function confirmDiscardObjectEdits() {
  return !hasUnsavedObjectEdits() || window.confirm(
    'Discard unsaved changes to the selected object?'
  );
}

function renderReadAttribute(key, value) {
  const longTextClass = isLongTextAttribute(key, value) ? ' long-text' : '';
  const renderedValue = String(value ?? '')
    ? escapeHtml(value)
    : '<span class="muted">Empty</span>';
  return `<section class="attribute-block"><h3>${escapeHtml(key)}</h3><div class="attribute-value${longTextClass}">${renderedValue}</div></section>`;
}

function renderAttributeEditor(key, value) {
  const multiline = isLongTextAttribute(key, value);
  const control = multiline
    ? `<textarea aria-label="${escapeHtml(key)}" data-original-value="${escapeHtml(value)}">${escapeHtml(value)}</textarea>`
    : `<input aria-label="${escapeHtml(key)}" data-original-value="${escapeHtml(value)}" value="${escapeHtml(value)}">`;
  return `<section class="attribute-block"><h3>${escapeHtml(key)}</h3><form class="attribute-editor" data-attribute="${escapeHtml(key)}">${control}<button type="submit">Save</button></form></section>`;
}

function setSelectedObjectTab(tab) {
  if (tab === selectedObjectTab) return;
  if (!confirmDiscardObjectEdits()) return;
  selectedObjectTab = tab;
  selectedObjectMode = 'read';
  objectEditFeedback = null;
  renderSelectedObject();
}

function renderSelectedObject() {
  const detail = document.getElementById('objectDetail');
  if (!selectedObjectId) {
    detail.classList.add('muted');
    detail.innerHTML = 'Select an object to inspect its attributes and direct relations.';
    return;
  }
  const object = objects.find(item => item.id === selectedObjectId);
  if (!object) {
    detail.classList.add('muted');
    detail.textContent = `Unknown object: ${selectedObjectId}`;
    return;
  }
  detail.classList.remove('muted');
  const direct = relations.filter(rel => rel.source === object.id || rel.target === object.id);
  const editableAttributes = editableAttributesFor(object);
  const editAction = editableAttributes.length
    ? `<button class="${selectedObjectMode === 'edit' ? 'secondary-action' : 'primary-action'}" type="button" data-action="${selectedObjectMode === 'edit' ? 'cancel-edit' : 'edit-object'}">${selectedObjectMode === 'edit' ? 'Done' : 'Edit'}</button>`
    : '';
  const attributes = Object.entries(object.attributes).map(([key, value]) =>
    selectedObjectMode === 'edit' && editableAttributes.includes(key)
      ? renderAttributeEditor(key, value)
      : renderReadAttribute(key, value)
  ).join('');
  const relationHtml = direct.length
    ? `<ul class="detail-relations">${direct.map(rel => {
        const otherId = rel.source === object.id ? rel.target : rel.source;
        return `<li><span class="badge">${escapeHtml(rel.area)}</span> ${escapeHtml(rel.source)} — ${escapeHtml(rel.relation)} → ${escapeHtml(rel.target)} <button class="link-button" data-object-id="${escapeHtml(otherId)}">select</button></li>`;
      }).join('')}</ul>`
    : '<p class="muted">No direct relations.</p>';
  const detailContent = selectedObjectTab === 'relations'
    ? relationHtml
    : `<dl class="object-metadata">
        <div><dt>Stable ID</dt><dd>${escapeHtml(object.id)} <span class="muted">(read-only)</span></dd></div>
        <div><dt>Type</dt><dd>${escapeHtml(object.type)} <span class="muted">(read-only)</span></dd></div>
        <div><dt>Source</dt><dd title="${escapeHtml(object.source_file)}">${escapeHtml(object.source_file)} <span class="muted">(read-only)</span></dd></div>
        <div><dt>Area</dt><dd>${escapeHtml(object.area)}</dd></div>
      </dl>
      ${objectEditFeedback ? `<div class="edit-feedback${objectEditFeedback.error ? ' error' : ''}" role="status">${escapeHtml(objectEditFeedback.message)}</div>` : ''}
      <div class="attribute-list">${attributes}</div>`;
  detail.innerHTML = `
    <div class="selected-object-header">
      <div class="selected-object-heading"><h2>Object Details — ${escapeHtml(object.id)}</h2><span class="badge">${escapeHtml(object.type)}</span><span>${escapeHtml(object.name)}</span></div>
      <div class="selected-object-actions">${selectedObjectTab === 'details' ? editAction : ''}</div>
    </div>
    <div class="detail-tabs" role="tablist" aria-label="Selected object sections">
      <button class="detail-tab${selectedObjectTab === 'details' ? ' active' : ''}" type="button" role="tab" aria-selected="${selectedObjectTab === 'details'}" data-detail-tab="details">Details</button>
      <button class="detail-tab${selectedObjectTab === 'relations' ? ' active' : ''}" type="button" role="tab" aria-selected="${selectedObjectTab === 'relations'}" data-detail-tab="relations">Relations</button>
    </div>
    <div role="tabpanel">${detailContent}</div>`;
  detail.querySelectorAll('[data-object-id]').forEach(button =>
    button.addEventListener('click', () => setSelectedObject(button.dataset.objectId)));
  detail.querySelectorAll('[data-detail-tab]').forEach(button =>
    button.addEventListener('click', () => setSelectedObjectTab(button.dataset.detailTab)));
  detail.querySelector('[data-action="edit-object"]')?.addEventListener('click', () => {
    selectedObjectMode = 'edit';
    objectEditFeedback = null;
    renderSelectedObject();
  });
  detail.querySelector('[data-action="cancel-edit"]')?.addEventListener('click', () => {
    if (!confirmDiscardObjectEdits()) return;
    selectedObjectMode = 'read';
    objectEditFeedback = null;
    renderSelectedObject();
  });
  detail.querySelectorAll('.attribute-editor').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault();
    const attribute = form.dataset.attribute;
    const input = form.querySelector('input, textarea');
    const button = form.querySelector('button');
    const expectedOldValue = object.attributes[attribute];
    button.disabled = true;
    input.disabled = true;
    objectEditFeedback = { message: 'Saving…', error: false };
    try {
      const snapshot = await dataProvider.updateObjectAttribute({
        object_id: object.id,
        attribute,
        value: input.value,
        expected_old_value: expectedOldValue
      });
      applyProjectSnapshot(snapshot, object.id);
      objectEditFeedback = { message: 'Saved', error: false };
    } catch (error) {
      if (error.code === 'conflict') {
        try {
          applyProjectSnapshot(await dataProvider.loadProject(), object.id);
        } catch (reloadError) {
          console.error('Reload after conflict failed.', reloadError);
        }
        objectEditFeedback = {
          message: 'The value changed since this page was loaded. Reloaded current value.',
          error: true
        };
      } else {
        objectEditFeedback = { message: error.message || 'The update failed.', error: true };
      }
    }
    renderSelectedObject();
  }));
}

function setSelectedObject(id) {
  const nextId = id && objects.some(object => object.id === id) ? id : null;
  if (nextId === selectedObjectId) return;
  if (!confirmDiscardObjectEdits()) return;
  selectedObjectId = nextId;
  selectedObjectMode = 'read';
  selectedObjectTab = 'details';
  objectEditFeedback = null;
  renderSelectedObject();
  activeRenderer?.onSelectionChanged?.(selectedObjectId);
  window.dispatchEvent(new CustomEvent('mbse-selection-change', {
    detail: { selectedObjectId }
  }));
}

function overviewRenderer(view, context) {
  return {
    mount(container) {
      const summary = context.model.summary;
      container.innerHTML = `${viewHeader(view)}
        <p class="muted">Engineering definition and project execution remain separate areas of one traceable project. Generated views are derived from the Markdown source model.</p>
        <div class="cards">
          <div class="card"><span class="muted">MBSE objects</span><strong>${summary.mbse_objects}</strong></div>
          <div class="card"><span class="muted">Project-management objects</span><strong>${summary.project_management_objects}</strong></div>
          <div class="card"><span class="muted">Relations</span><strong>${summary.relations}</strong></div>
          <div class="card"><span class="muted">Supporting data tables</span><strong>${summary.tables}</strong></div>
          <div class="card"><span class="muted">Validation findings</span><strong>${summary.validation_findings}</strong></div>
        </div>`;
    }
  };
}

function objectsRenderer(view, context) {
  let rowsElement;
  let search;
  let typeFilter;
  const configuredArea = view.config?.area || '';
  const configuredTypes = Array.isArray(view.config?.types) ? view.config.types : [];
  const searchId = view.config?.search_id || `${view.id}Search`;
  const viewObjects = context.model.objects.filter(object =>
    (!configuredArea || object.area === configuredArea) &&
    (!configuredTypes.length || configuredTypes.includes(object.type)));

  function renderRows() {
    const query = search.value.trim().toLowerCase();
    const type = typeFilter.value;
    const rows = viewObjects.filter(object => {
      const searchable = JSON.stringify(object).toLowerCase();
      return (!type || object.type === type) && (!query || searchable.includes(query));
    });
    rowsElement.innerHTML = rows.map(object => `
      <tr class="object-row${object.id === selectedObjectId ? ' selected' : ''}" data-id="${escapeHtml(object.id)}">
        <td><strong>${escapeHtml(object.id)}</strong></td>
        <td><span class="badge">${escapeHtml(object.type)}</span></td>
        <td>${escapeHtml(object.name)}</td>
        <td>${escapeHtml(object.status)}</td>
        <td>${escapeHtml(object.source_file)}</td>
      </tr>`).join('');
    rowsElement.querySelectorAll('.object-row').forEach(row =>
      row.addEventListener('click', () => context.setSelectedObject(row.dataset.id)));
  }

  return {
    mount(container) {
      container.innerHTML = `${viewHeader(view)}
        <div class="toolbar">
          <input id="${escapeHtml(searchId)}" type="search" placeholder="Search objects…">
          <select><option value="">All object types</option></select>
        </div>
        <div class="table-wrap"><table><thead><tr><th>ID</th><th>Type</th><th>Name</th><th>Status</th><th>Source</th></tr></thead><tbody></tbody></table></div>`;
      search = container.querySelector('input[type="search"]');
      typeFilter = container.querySelector('select');
      rowsElement = container.querySelector('tbody');
      [...new Set(viewObjects.map(object => object.type))].sort().forEach(type => {
        const option = document.createElement('option');
        option.value = type;
        option.textContent = type;
        typeFilter.appendChild(option);
      });
      search.addEventListener('input', renderRows);
      typeFilter.addEventListener('change', renderRows);
      renderRows();
    },
    onSelectionChanged() {
      if (rowsElement) renderRows();
    }
  };
}

function tablesRenderer(view, context) {
  let container;
  let search;
  function renderTables() {
    const query = search.value.trim().toLowerCase();
    const tables = context.model.tables.filter(table =>
      !query || JSON.stringify(table).toLowerCase().includes(query));
    const content = container.querySelector('[data-table-content]');
    if (!tables.length) {
      content.innerHTML = '<div class="card muted">No supporting data tables match the current filter.</div>';
      return;
    }
    content.innerHTML = tables.map(table => {
      const headers = table.headers.map(header => `<th>${escapeHtml(header)}</th>`).join('');
      const rows = table.rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('');
      return `<div class="data-block"><h3>${escapeHtml(table.source_file)}</h3><span class="badge">${escapeHtml(table.area)}</span><div class="table-wrap"><table><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table></div></div>`;
    }).join('');
  }
  return {
    mount(target) {
      container = target;
      container.innerHTML = `${viewHeader(view)}<div class="toolbar"><input id="dataSearch" type="search" placeholder="Search supporting project data…"></div><div data-table-content></div>`;
      search = container.querySelector('input');
      search.addEventListener('input', renderTables);
      renderTables();
    }
  };
}

function relationsRenderer(view, context) {
  let container;
  let search;
  let areaFilter;
  function renderRelations() {
    const query = search.value.trim().toLowerCase();
    const area = areaFilter.value;
    const rows = context.model.relations.filter(rel =>
      (!area || rel.area === area) && (!query || JSON.stringify(rel).toLowerCase().includes(query)));
    const tbody = container.querySelector('tbody');
    tbody.innerHTML = rows.map(rel => `
      <tr><td><span class="badge">${escapeHtml(rel.area)}</span></td><td><button class="link-button" data-object-id="${escapeHtml(rel.source)}">${escapeHtml(rel.source)}</button></td><td>${escapeHtml(rel.relation)}</td><td><button class="link-button" data-object-id="${escapeHtml(rel.target)}">${escapeHtml(rel.target)}</button></td><td>${escapeHtml(rel.source_file)}</td></tr>`).join('');
    tbody.querySelectorAll('[data-object-id]').forEach(button =>
      button.addEventListener('click', () => context.setSelectedObject(button.dataset.objectId)));
  }
  return {
    mount(target) {
      container = target;
      const areas = [...new Set(context.model.relations.map(rel => rel.area))].sort();
      container.innerHTML = `${viewHeader(view)}
        <div class="toolbar"><input id="relationSearch" type="search" placeholder="Search source, relation or target…"><select id="relationAreaFilter"><option value="">All relation areas</option></select></div>
        <div class="table-wrap"><table><thead><tr><th>Area</th><th>Source</th><th>Relation</th><th>Target</th><th>Source file</th></tr></thead><tbody></tbody></table></div>`;
      search = container.querySelector('#relationSearch');
      areaFilter = container.querySelector('#relationAreaFilter');
      areas.forEach(area => {
        const option = document.createElement('option');
        option.value = area;
        option.textContent = area;
        areaFilter.appendChild(option);
      });
      search.addEventListener('input', renderRelations);
      areaFilter.addEventListener('change', renderRelations);
      renderRelations();
    }
  };
}

function validationRenderer(view, context) {
  return {
    mount(container) {
      if (!context.model.validation.length) {
        container.innerHTML = `${viewHeader(view)}<div class="card"><span class="severity-OK">OK</span> · No validation findings.</div>`;
        return;
      }
      const rows = context.model.validation.map(item => {
        const severity = ['ERROR', 'WARNING'].includes(item.severity) ? item.severity : 'OK';
        return `<tr><td class="severity-${severity}">${escapeHtml(item.severity)}</td><td>${escapeHtml(item.message)}</td></tr>`;
      }).join('');
      container.innerHTML = `${viewHeader(view)}<div class="table-wrap"><table><thead><tr><th>Severity</th><th>Finding</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }
  };
}

function mermaidRenderer(view, context) {
  let disposed = false;
  return {
    mount(container) {
      disposed = false;
      const source = context.assets[view.source];
      if (typeof source !== 'string') {
        container.innerHTML = `${viewHeader(view)}<div class="scaffold muted">Mermaid source is unavailable: ${escapeHtml(view.source || '(no source)')}</div>`;
        return;
      }
      container.innerHTML = `${viewHeader(view)}<div class="graph"><p class="muted" data-mermaid-status>Rendering diagram…</p><pre class="mermaid">${escapeHtml(source)}</pre></div><details><summary>Mermaid source</summary><pre>${escapeHtml(source)}</pre></details>`;
      const graph = container.querySelector('.mermaid');
      const status = container.querySelector('[data-mermaid-status]');
      window.mbseMermaidReady?.then(async mermaid => {
        if (disposed) return;
        if (!mermaid) {
          graph.classList.remove('mermaid');
          status.textContent = 'The local Mermaid dependency is unavailable. Source remains available below.';
          return;
        }
        try {
          await mermaid.run({ nodes: [graph] });
          if (!disposed) status.remove();
        } catch (error) {
          console.error('The Mermaid view could not be rendered.', error);
          if (!disposed) {
            graph.classList.remove('mermaid');
            status.textContent = 'The Mermaid diagram could not be rendered. Source remains available below.';
          }
        }
      });
    },
    onSelectionChanged(id) {
      this.selectedObjectId = id;
    },
    unmount() {
      disposed = true;
    }
  };
}

function safeAssetSource(source) {
  const normalized = String(source || '').replaceAll('\\\\', '/');
  if (!normalized || normalized.startsWith('/') || normalized.startsWith('//') || /^[a-z][a-z0-9+.-]*:/i.test(normalized)) return null;
  if (normalized.split('/').some(part => !part || part === '.' || part === '..')) return null;
  return normalized;
}

function base64ToArrayBuffer(encoded) {
  const decoded = atob(encoded);
  const bytes = new Uint8Array(decoded.length);
  for (let index = 0; index < decoded.length; index += 1) {
    bytes[index] = decoded.charCodeAt(index);
  }
  return bytes.buffer;
}

function sanitizedSvgElement(source) {
  const parsed = new DOMParser().parseFromString(source, 'image/svg+xml');
  if (parsed.querySelector('parsererror') || parsed.documentElement.localName.toLowerCase() !== 'svg') return null;
  const blockedElements = new Set([
    'script', 'foreignobject', 'style', 'iframe', 'object', 'embed', 'link', 'meta',
    'audio', 'video', 'image', 'animate', 'animatemotion', 'animatetransform', 'set', 'discard'
  ]);
  const elements = [parsed.documentElement, ...parsed.documentElement.querySelectorAll('*')];
  elements.forEach(element => {
    if (element !== parsed.documentElement && blockedElements.has(element.localName.toLowerCase())) {
      element.remove();
      return;
    }
    [...element.attributes].forEach(attribute => {
      const name = attribute.localName.toLowerCase();
      const value = attribute.value;
      const compactValue = value.replace(/\\s/g, '');
      const lowerValue = compactValue.toLowerCase();
      const fragmentPaint = /^url\\(#[A-Za-z_][\\w.-]*\\)$/i.test(compactValue);
      const unsafeUri = ['href', 'src'].includes(name) && value.trim() && !value.trim().startsWith('#');
      if (name === 'style' || name.startsWith('on') || lowerValue.includes('javascript:') ||
          unsafeUri || (lowerValue.includes('url(') && !fragmentPaint)) {
        element.removeAttribute(attribute.name);
      }
    });
  });
  return document.importNode(parsed.documentElement, true);
}

function svgRenderer(view, context) {
  let host;
  let clickHandler;
  return {
    mount(container) {
      const source = safeAssetSource(view.source);
      container.innerHTML = `${viewHeader(view)}<div class="scaffold" data-svg-host></div>`;
      host = container.querySelector('[data-svg-host]');
      if (!source) {
        host.innerHTML = '<p class="muted">SVG source is missing or unsafe.</p>';
        return;
      }
      const assetError = context.assetErrors[source];
      if (typeof assetError === 'string') {
        host.innerHTML = `<p class="muted">${escapeHtml(assetError)}</p>`;
        return;
      }
      const svgSource = context.assets[source];
      if (typeof svgSource !== 'string') {
        host.innerHTML = '<p class="muted">Embedded SVG source is unavailable.</p>';
        return;
      }
      const svg = sanitizedSvgElement(svgSource);
      if (!svg) {
        host.innerHTML = '<p class="muted">SVG source is invalid or unsafe.</p>';
        return;
      }
      host.classList.add('svg-host');
      svg.classList.add('engineering-svg');
      host.appendChild(svg);
      clickHandler = event => {
        const element = event.target.closest?.('[data-mbse-id]');
        if (element && host.contains(element)) {
          context.setSelectedObject(element.getAttribute('data-mbse-id'));
        }
      };
      host.addEventListener('click', clickHandler);
    },
    onSelectionChanged(id) {
      host?.querySelectorAll('[data-mbse-id]').forEach(element =>
        element.classList.toggle('mbse-selected', element.getAttribute('data-mbse-id') === id));
    },
    unmount() {
      if (host && clickHandler) host.removeEventListener('click', clickHandler);
      host = null;
      clickHandler = null;
    }
  };
}

function gltfRenderer(view, context) {
  let host;
  let status;
  let renderer;
  let scene;
  let camera;
  let controls;
  let modelRoot;
  let loadedScenes = [];
  let grid;
  let raycaster;
  let pointerDownHandler;
  let pointerMoveHandler;
  let pointerUpHandler;
  let pointerCancelHandler;
  let pointerStart = null;
  let resizeObserver;
  let animationFrame = 0;
  let selectedId = null;
  let disposed = false;
  let THREE;
  const clickMovementThreshold = 5;
  const highlightedMaterials = new Map();

  function setStatus(message) {
    if (!host) return;
    if (!status || !host.contains(status)) {
      status = document.createElement('p');
      status.className = 'gltf-status';
      host.appendChild(status);
    }
    status.textContent = message;
  }

  function resolveMbseId(object) {
    let current = object;
    while (current) {
      if (current.userData?.mbse_id) return String(current.userData.mbse_id);
      current = current.parent;
    }
    return null;
  }

  function restoreHighlights() {
    highlightedMaterials.forEach((original, mesh) => {
      const highlighted = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      highlighted.forEach(material => material?.dispose?.());
      mesh.material = original;
    });
    highlightedMaterials.clear();
  }

  function highlightedMaterial(material) {
    const clone = material.clone();
    if (clone.emissive) {
      clone.emissive.setHex(0x2f7df6);
      clone.emissiveIntensity = 0.8;
    } else if (clone.color) {
      clone.color.lerp(new THREE.Color(0x2f7df6), 0.45);
    }
    return clone;
  }

  function applyHighlight(id) {
    restoreHighlights();
    if (!id || !modelRoot) return;
    modelRoot.traverse(object => {
      if (!object.isMesh || resolveMbseId(object) !== id) return;
      const original = object.material;
      highlightedMaterials.set(object, original);
      object.material = Array.isArray(original)
        ? original.map(highlightedMaterial)
        : highlightedMaterial(original);
    });
  }

  function resize() {
    if (!host || !renderer || !camera) return;
    const width = Math.max(host.clientWidth, 1);
    const height = Math.max(host.clientHeight, 1);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  function renderLoop() {
    if (disposed || !renderer || !scene || !camera) return;
    animationFrame = requestAnimationFrame(renderLoop);
    controls?.update();
    renderer.render(scene, camera);
  }

  function disposeObjectResources(roots) {
    const geometries = new Set();
    const materials = new Set();
    const textures = new Set();
    roots.forEach(root => root?.traverse(object => {
      if (object.geometry?.dispose) geometries.add(object.geometry);
      if (object.skeleton?.boneTexture?.dispose) textures.add(object.skeleton.boneTexture);
      const objectMaterials = Array.isArray(object.material)
        ? object.material
        : [object.material];
      objectMaterials.filter(Boolean).forEach(material => {
        materials.add(material);
        Object.values(material).forEach(value => {
          if (value?.isTexture) textures.add(value);
          if (Array.isArray(value)) {
            value.filter(item => item?.isTexture).forEach(texture => textures.add(texture));
          }
        });
      });
    }));
    textures.forEach(texture => texture.dispose());
    geometries.forEach(geometry => geometry.dispose());
    materials.forEach(material => material.dispose());
  }

  function disposeSceneResources() {
    restoreHighlights();
    disposeObjectResources(loadedScenes);
    loadedScenes = [];
    if (grid) {
      grid.geometry?.dispose();
      grid.material?.dispose();
    }
  }

  function removePointerListeners() {
    const canvas = renderer?.domElement;
    if (!canvas) return;
    if (pointerDownHandler) canvas.removeEventListener('pointerdown', pointerDownHandler);
    if (pointerMoveHandler) canvas.removeEventListener('pointermove', pointerMoveHandler);
    if (pointerUpHandler) canvas.removeEventListener('pointerup', pointerUpHandler);
    if (pointerCancelHandler) canvas.removeEventListener('pointercancel', pointerCancelHandler);
  }

  function selectAtPointer(event) {
    if (!modelRoot || !renderer || !raycaster || !camera) return;
    const bounds = renderer.domElement.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const pointer = new THREE.Vector2(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      -((event.clientY - bounds.top) / bounds.height) * 2 + 1
    );
    raycaster.setFromCamera(pointer, camera);
    for (const intersection of raycaster.intersectObject(modelRoot, true)) {
      const mbseId = resolveMbseId(intersection.object);
      if (mbseId) {
        context.setSelectedObject(mbseId);
        return;
      }
    }
  }

  function installPointerListeners() {
    const canvas = renderer.domElement;
    pointerDownHandler = event => {
      if (event.button !== 0 || event.isPrimary === false) return;
      pointerStart = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        moved: false
      };
    };
    pointerMoveHandler = event => {
      if (!pointerStart || event.pointerId !== pointerStart.pointerId) return;
      if (Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) >= clickMovementThreshold) {
        pointerStart.moved = true;
      }
    };
    pointerUpHandler = event => {
      if (!pointerStart || event.pointerId !== pointerStart.pointerId) return;
      const movement = Math.hypot(
        event.clientX - pointerStart.x,
        event.clientY - pointerStart.y
      );
      const isClick = !pointerStart.moved && movement < clickMovementThreshold;
      pointerStart = null;
      if (isClick) selectAtPointer(event);
    };
    pointerCancelHandler = event => {
      if (pointerStart?.pointerId === event.pointerId) pointerStart = null;
    };
    canvas.addEventListener('pointerdown', pointerDownHandler);
    canvas.addEventListener('pointermove', pointerMoveHandler);
    canvas.addEventListener('pointerup', pointerUpHandler);
    canvas.addEventListener('pointercancel', pointerCancelHandler);
  }

  function clearPointerState() {
    pointerStart = null;
    pointerDownHandler = null;
    pointerMoveHandler = null;
    pointerUpHandler = null;
    pointerCancelHandler = null;
  }

  function cleanupRenderer() {
    if (animationFrame) cancelAnimationFrame(animationFrame);
    animationFrame = 0;
    resizeObserver?.disconnect();
    removePointerListeners();
    controls?.dispose();
    disposeSceneResources();
    renderer?.dispose();
    renderer?.forceContextLoss?.();
    renderer = null;
    scene = null;
    camera = null;
    controls = null;
    modelRoot = null;
    grid = null;
    raycaster = null;
    clearPointerState();
    resizeObserver = null;
  }

  async function initialize(modules, arrayBuffer) {
    THREE = modules.THREE;
    const { GLTFLoader, OrbitControls } = modules;
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xeef1f5);
    camera = new THREE.PerspectiveCamera(42, 1, 0.01, 1000);
    renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const notice = host.querySelector('.gltf-notice');
    host.replaceChildren(renderer.domElement);
    if (notice) host.appendChild(notice);

    scene.add(new THREE.HemisphereLight(0xf8fbff, 0x53606c, 2.2));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.8);
    keyLight.position.set(5, 8, 6);
    scene.add(keyLight);

    const loader = new GLTFLoader();
    const gltf = await new Promise((resolve, reject) =>
      loader.parse(arrayBuffer, '', resolve, reject));
    const parsedScenes = gltf.scenes?.length ? gltf.scenes : [gltf.scene];
    if (disposed) {
      disposeObjectResources(parsedScenes);
      return;
    }
    loadedScenes = parsedScenes;
    modelRoot = gltf.scene;
    const viewerScale = Number(view.config?.viewer_scale ?? 1);
    if (!Number.isFinite(viewerScale) || viewerScale <= 0) {
      throw new Error('The GLB viewer scale must be finite and positive.');
    }
    modelRoot.scale.setScalar(viewerScale);
    modelRoot.traverse(object => {
      if (object.userData?.mbse_id) object.userData.mbse_id = String(object.userData.mbse_id);
    });
    scene.add(modelRoot);

    const bounds = new THREE.Box3().setFromObject(modelRoot);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z, 1);
    camera.near = Math.max(maxDimension / 1000, 0.01);
    camera.far = maxDimension * 100;
    camera.position.set(
      center.x + maxDimension * 1.15,
      center.y + maxDimension * 0.85,
      center.z + maxDimension * 1.35
    );
    camera.lookAt(center);
    camera.updateProjectionMatrix();

    controls = new OrbitControls(camera, renderer.domElement);
    controls.target.copy(center);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = true;
    controls.update();

    grid = new THREE.GridHelper(maxDimension * 2, 20, 0x8d99a8, 0xc6cdd6);
    grid.position.y = -0.005;
    scene.add(grid);

    raycaster = new THREE.Raycaster();
    installPointerListeners();
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();
    applyHighlight(selectedId);
    renderLoop();
  }

  return {
    mount(container) {
      disposed = false;
      const source = safeAssetSource(view.source);
      const notice = view.config?.notice
        ? `<p class="gltf-notice">${escapeHtml(view.config.notice)}</p>`
        : '';
      container.innerHTML = `${viewHeader(view)}<div class="scaffold gltf-host" data-gltf-host>${notice}<p class="gltf-status">Loading conceptual 3D view…</p></div>`;
      host = container.querySelector('[data-gltf-host]');
      status = host.querySelector('.gltf-status');
      if (!source) {
        setStatus('GLB source is missing or unsafe.');
        return;
      }
      const encoded = context.binaryAssets[source];
      if (typeof encoded !== 'string') {
        setStatus('Embedded GLB data is unavailable.');
        return;
      }
      const arrayBuffer = base64ToArrayBuffer(encoded);
      Promise.resolve(window.mbseThreeReady).then(async modules => {
        if (disposed) return;
        if (!modules) {
          setStatus('The local Three.js dependency is unavailable. Regenerate the viewer bundle; other views remain available.');
          return;
        }
        try {
          await initialize(modules, arrayBuffer);
        } catch (error) {
          console.error('The conceptual GLB view could not be rendered.', error);
          cleanupRenderer();
          if (!disposed) setStatus('The conceptual 3D model could not be rendered. Other viewer views remain available.');
        }
      });
    },
    onSelectionChanged(id) {
      selectedId = id;
      applyHighlight(id);
    },
    unmount() {
      disposed = true;
      cleanupRenderer();
      host = null;
      status = null;
    }
  };
}

function scaffoldRenderer(kind) {
  let selectionValue;
  return (view) => ({
    mount(container) {
      container.innerHTML = `${viewHeader(view)}<div class="scaffold"><p><strong>${escapeHtml(kind)} renderer is not available in this viewer.</strong></p><p class="muted">Source: ${escapeHtml(view.source || '(not specified)')}</p><p class="muted" data-selection-value>No object selected.</p></div>`;
      selectionValue = container.querySelector('[data-selection-value]');
    },
    onSelectionChanged(id) {
      if (selectionValue) selectionValue.textContent = id ? `Selected object: ${id}` : 'No object selected.';
    }
  });
}

function unsupportedRenderer(view) {
  return {
    mount(container) {
      container.innerHTML = `${viewHeader(view)}<div class="scaffold"><strong>Unsupported view type</strong><p class="muted">No renderer is registered for “${escapeHtml(view.type)}”. The rest of the viewer remains available.</p></div>`;
    }
  };
}

const rendererFactories = {
  overview: overviewRenderer,
  objects: objectsRenderer,
  tables: tablesRenderer,
  relations: relationsRenderer,
  validation: validationRenderer,
  mermaid: mermaidRenderer,
  graph: scaffoldRenderer('Graph'),
  svg: svgRenderer,
  gltf: gltfRenderer
};

let viewerContext = null;

function activateView(viewId) {
  const view = viewerManifest.views.find(item => item.id === viewId);
  if (!view) return;
  activeRenderer?.unmount?.();
  activeViewId = view.id;
  document.querySelectorAll('[data-view-id]').forEach(button =>
    button.classList.toggle('active', button.dataset.viewId === activeViewId));
  const container = document.getElementById('viewContent');
  container.replaceChildren();
  const factory = rendererFactories[view.type] || unsupportedRenderer;
  try {
    activeRenderer = factory(view, viewerContext) || {};
    activeRenderer.mount?.(container);
    activeRenderer.onSelectionChanged?.(selectedObjectId);
  } catch (error) {
    console.error(`Failed to render view ${view.id}`, error);
    activeRenderer = unsupportedRenderer(view);
    activeRenderer.mount(container);
  }
}

function renderNavigation() {
  const navigation = document.getElementById('viewNavigation');
  const groups = new Map();
  viewerManifest.views.forEach(view => {
    if (!groups.has(view.group)) groups.set(view.group, []);
    groups.get(view.group).push(view);
  });
  groups.forEach((views, group) => {
    const section = document.createElement('section');
    section.className = 'nav-group';
    const heading = document.createElement('h2');
    heading.textContent = group;
    section.appendChild(heading);
    views.forEach(view => {
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.viewId = view.id;
      button.textContent = view.title;
      button.addEventListener('click', () => activateView(view.id));
      section.appendChild(button);
    });
    navigation.appendChild(section);
  });
}

function registerRenderer(type, factory) {
  if (!type || typeof factory !== 'function') throw new TypeError('A renderer type and factory function are required.');
  rendererFactories[type] = factory;
  const activeView = viewerManifest.views.find(view => view.id === activeViewId);
  if (activeView?.type === type) activateView(activeViewId);
}

function applyProjectSnapshot(snapshot, preserveObjectId = selectedObjectId) {
  viewerManifest = snapshot.manifest;
  viewerModel = snapshot.model;
  objects = viewerModel.objects;
  relations = viewerModel.relations;
  supportingTables = viewerModel.tables;
  findings = viewerModel.validation;
  selectedObjectId = preserveObjectId && objects.some(object => object.id === preserveObjectId)
    ? preserveObjectId
    : null;
  viewerContext = {
    model: viewerModel,
    manifest: viewerManifest,
    assets: snapshot.assets,
    binaryAssets: snapshot.binaryAssets,
    assetErrors: snapshot.assetErrors,
    capabilities: snapshot.capabilities,
    setSelectedObject,
    getSelectedObjectId: () => selectedObjectId
  };
  if (window.mbseViewer) {
    window.mbseViewer.capabilities = snapshot.capabilities;
    window.mbseViewer.model = viewerModel;
    window.mbseViewer.manifest = viewerManifest;
  }
  __AUTHORING_SNAPSHOT_HOOK__
  document.getElementById('modelCounts').textContent = `${viewerModel.summary.objects} objects · ${viewerModel.summary.relations} relations`;
  if (activeViewId) activateView(activeViewId);
}

async function bootstrapViewer() {
  __LOAD_PROJECT__
  applyProjectSnapshot(snapshot, null);

  window.mbseViewer = {
    getSelectedObjectId: () => selectedObjectId,
    setSelectedObject,
    registerRenderer,
    activateView,
    provider: __PROVIDER_REF__,
    capabilities: snapshot.capabilities,
    model: viewerModel,
    manifest: viewerManifest
  };

  renderNavigation();
  renderSelectedObject();
  if (viewerManifest.default_view) activateView(viewerManifest.default_view);
  else document.getElementById('viewContent').innerHTML = '<div class="card muted">This viewer manifest contains no views.</div>';
}

bootstrapViewer().catch(error => {
  console.error('__LOAD_ERROR__', error);
  document.getElementById('viewContent').innerHTML = '<div class="card muted">__LOAD_ERROR__</div>';
});
</script>
</body>
</html>
"""

    if data_provider == "embedded":
        provider_source = """const embeddedViewerManifest = __MANIFEST_JSON__;
const embeddedViewerModel = __MODEL_JSON__;
const embeddedViewAssets = __ASSETS_JSON__;
const embeddedBinaryViewAssets = __BINARY_ASSETS_JSON__;
const viewAssetErrors = __ASSET_ERRORS_JSON__;

class EmbeddedDataProvider {
  constructor(snapshot) {
    this.snapshot = snapshot;
    this.capabilities = Object.freeze({ read: true, write: false });
  }

  async loadProject() {
    return { ...this.snapshot, capabilities: this.capabilities };
  }
}

const embeddedDataProvider = new EmbeddedDataProvider({
  manifest: embeddedViewerManifest,
  model: embeddedViewerModel,
  assets: embeddedViewAssets,
  binaryAssets: embeddedBinaryViewAssets,
  assetErrors: viewAssetErrors
});
const dataProvider = embeddedDataProvider;"""
        mode_label = "MBSE Lite · local read-only viewer"
        load_project = "const snapshot = await embeddedDataProvider.loadProject();"
        provider_ref = "embeddedDataProvider"
        load_error = "The embedded project snapshot could not be loaded."
        authoring_ui = ""
        authoring_source = ""
        authoring_snapshot_hook = ""
    else:
        provider_source = """class HttpProviderError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = 'HttpProviderError';
    this.status = status;
    this.payload = payload;
    this.code = payload?.error || 'server_error';
  }
}

class HttpDataProvider {
  constructor() {
    this.capabilities = Object.freeze({ read: true, write: true });
  }

  withServerCapabilities(snapshot) {
    const capabilities = { read: true, write: true };
    if (snapshot?.authoring?.requirements?.create?.enabled === true) {
      capabilities.createRequirement = true;
    }
    this.capabilities = Object.freeze(capabilities);
    return { ...snapshot, capabilities: this.capabilities };
  }

  async request(path, options = {}) {
    let response;
    try {
      response = await fetch(path, { credentials: 'same-origin', ...options });
    } catch (error) {
      throw new HttpProviderError('Could not reach the local MBSE Lite server.', 0, null);
    }
    let payload = null;
    try { payload = await response.json(); } catch (error) { /* concise fallback below */ }
    if (!response.ok) {
      throw new HttpProviderError(payload?.message || `Server request failed (${response.status}).`, response.status, payload);
    }
    return payload;
  }

  async loadProject() {
    return this.withServerCapabilities(
      await this.request('/api/project', { headers: { Accept: 'application/json' } })
    );
  }

  async updateObjectAttribute(command) {
    return this.request('/api/object-attribute', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(command)
    });
  }

  async createRequirement(command) {
    if (this.capabilities.createRequirement !== true) {
      throw new HttpProviderError('Requirement creation is not enabled for this project.', 422, null);
    }
    const result = await this.request('/api/requirements', {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(command)
    });
    result.project = this.withServerCapabilities(result.project);
    return result;
  }
}

const httpDataProvider = new HttpDataProvider();
const dataProvider = httpDataProvider;"""
        mode_label = "MBSE Lite · local editable application"
        load_project = "const snapshot = await httpDataProvider.loadProject();"
        provider_ref = "httpDataProvider"
        load_error = "The current project snapshot could not be loaded."
        authoring_ui = """<button id="createRequirementButton" class="primary-action" type="button" aria-describedby="createRequirementReason" hidden>Create Requirement</button><span id="createRequirementReason" class="muted" hidden></span>
<dialog id="requirementDialog" class="requirement-dialog" aria-labelledby="requirementDialogTitle">
  <form id="requirementForm" method="dialog">
    <h2 id="requirementDialogTitle">Create Requirement</h2>
    <p class="muted">The stable ID is assigned by MBSE Lite. No relation is created automatically.</p>
    <div class="requirement-field"><label for="suggestedRequirementId">Suggested ID</label><input id="suggestedRequirementId" readonly></div>
    <div id="requirementFormFields" class="requirement-form-fields"></div>
    <p id="requirementCreationFeedback" class="creation-feedback" role="status"></p>
    <div class="dialog-actions"><button id="cancelRequirementButton" type="button">Cancel</button><button type="submit">Save</button></div>
  </form>
</dialog>"""
        authoring_source = r"""
const createRequirementButton = document.getElementById('createRequirementButton');
const createRequirementReason = document.getElementById('createRequirementReason');
const requirementDialog = document.getElementById('requirementDialog');
const requirementForm = document.getElementById('requirementForm');
const requirementFormFields = document.getElementById('requirementFormFields');
const suggestedRequirementId = document.getElementById('suggestedRequirementId');
const requirementCreationFeedback = document.getElementById('requirementCreationFeedback');
let requirementCreationMetadata = null;

function syncRequirementCreation(snapshot) {
  requirementCreationMetadata = snapshot?.authoring?.requirements?.create || null;
  createRequirementButton.hidden = false;
  createRequirementButton.disabled = requirementCreationMetadata?.enabled !== true;
  createRequirementButton.title = requirementCreationMetadata?.enabled
    ? 'Create one Requirement in the authoritative Markdown table.'
    : (requirementCreationMetadata?.reason || 'Requirement creation is unavailable.');
  createRequirementReason.hidden = requirementCreationMetadata?.enabled === true;
  createRequirementReason.textContent = requirementCreationMetadata?.enabled
    ? ''
    : createRequirementButton.title;
}

function renderRequirementForm(metadata, preservedValues = null) {
  suggestedRequirementId.value = metadata.suggested_id || '';
  requirementForm.dataset.expectedTableRevision = metadata.expected_table_revision || '';
  requirementFormFields.innerHTML = '';
  metadata.columns.forEach(column => {
    const wrapper = document.createElement('div');
    wrapper.className = 'requirement-field';
    const label = document.createElement('label');
    const inputId = `requirement-${column.name.replace(/[^A-Za-z0-9_-]/g, '-')}`;
    label.htmlFor = inputId;
    label.textContent = column.name + (column.required ? ' *' : '');
    const isRequirementText = column.name === 'Requirement' || column.name === 'Description';
    const input = document.createElement(isRequirementText ? 'textarea' : 'input');
    input.id = inputId;
    input.name = column.name;
    input.required = column.required === true;
    input.value = preservedValues?.[column.name] ?? column.default ?? '';
    wrapper.append(label, input);
    requirementFormFields.appendChild(wrapper);
  });
}

function currentRequirementValues() {
  return Object.fromEntries(
    [...requirementFormFields.querySelectorAll('[name]')].map(input => [input.name, input.value])
  );
}

createRequirementButton.addEventListener('click', () => {
  if (requirementCreationMetadata?.enabled !== true) return;
  renderRequirementForm(requirementCreationMetadata);
  requirementCreationFeedback.textContent = '';
  requirementCreationFeedback.classList.remove('error');
  if (typeof requirementDialog.showModal === 'function') requirementDialog.showModal();
  else requirementDialog.setAttribute('open', '');
});

document.getElementById('cancelRequirementButton').addEventListener('click', () => {
  if (typeof requirementDialog.close === 'function') requirementDialog.close();
  else requirementDialog.removeAttribute('open');
});

requirementForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (!requirementForm.reportValidity()) return;
  const values = currentRequirementValues();
  const saveButton = requirementForm.querySelector('button[type="submit"]');
  saveButton.disabled = true;
  requirementCreationFeedback.textContent = 'Saving…';
  requirementCreationFeedback.classList.remove('error');
  try {
    const result = await dataProvider.createRequirement({
      values,
      expected_table_revision: requirementForm.dataset.expectedTableRevision
    });
    objectEditFeedback = { message: 'Requirement created', error: false };
    applyProjectSnapshot(result.project, result.created_object_id);
    renderSelectedObject();
    if (typeof requirementDialog.close === 'function') requirementDialog.close();
    else requirementDialog.removeAttribute('open');
  } catch (error) {
    if (error.status === 409 && error.payload?.reason === 'requirements_table_changed') {
      const freshProject = error.payload.project;
      if (freshProject) {
        const preserved = values;
        const normalized = dataProvider.withServerCapabilities(freshProject);
        applyProjectSnapshot(normalized, selectedObjectId);
        const currentMetadata = normalized.authoring?.requirements?.create;
        if (currentMetadata?.enabled) renderRequirementForm(currentMetadata, preserved);
      }
      requirementCreationFeedback.textContent = 'Requirements changed since the form was opened. Review the current project and save again.';
    } else {
      requirementCreationFeedback.textContent = error.message || 'Requirement creation failed.';
    }
    requirementCreationFeedback.classList.add('error');
  } finally {
    saveButton.disabled = false;
  }
});
"""
        authoring_snapshot_hook = "syncRequirementCreation(snapshot);"

    provider_source = (
        provider_source.replace("__MANIFEST_JSON__", _json_for_html(manifest))
        .replace("__MODEL_JSON__", _json_for_html(viewer_model))
        .replace("__ASSETS_JSON__", _json_for_html(embedded_assets))
        .replace("__BINARY_ASSETS_JSON__", _json_for_html(embedded_binary_assets))
        .replace("__ASSET_ERRORS_JSON__", _json_for_html(asset_errors))
    )
    replacements = {
        "__TITLE__": title,
        "__MANIFEST_JSON__": _json_for_html(manifest),
        "__MODEL_JSON__": _json_for_html(viewer_model),
        "__ASSETS_JSON__": _json_for_html(embedded_assets),
        "__BINARY_ASSETS_JSON__": _json_for_html(embedded_binary_assets),
        "__ASSET_ERRORS_JSON__": _json_for_html(asset_errors),
        "__THREE_ASSET_PATH__": THREE_ASSET_PATH,
        "__MERMAID_ASSET_PATH__": MERMAID_ASSET_PATH,
        "__MODE_LABEL__": mode_label,
        "__PROVIDER_SOURCE__": provider_source,
        "__AUTHORING_UI__": authoring_ui,
        "__AUTHORING_SOURCE__": authoring_source,
        "__AUTHORING_SNAPSHOT_HOOK__": authoring_snapshot_hook,
        "__LOAD_PROJECT__": load_project,
        "__PROVIDER_REF__": provider_ref,
        "__LOAD_ERROR__": load_error,
    }
    for token, value in replacements.items():
        html = html.replace(token, value)

    output_path.write_text(html, encoding="utf-8")
