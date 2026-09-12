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
) -> None:
    """Generate a read-only, manifest-driven web viewer bundle.

    ``output`` remains the HTML path for backwards compatibility. The bundle
    also contains sibling ``model.json``, ``viewer.json`` and referenced view
    assets. Text assets and selected binary renderer assets are embedded in the
    HTML so the viewer still works when opened directly through ``file://``.
    """

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    assets: dict[str, str | bytes] = {}
    if views is None:
        definitions = list(default_view_definitions())
        assets.update(build_default_view_assets(model))
        generated = build_generated_views(model)
        definitions.extend(generated.views)
        assets.update(generated.assets)
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
.layout { display: grid; grid-template-columns: 220px minmax(0, 1fr) 330px; min-height: calc(100vh - 74px); }
nav { padding: 1rem; border-right: 1px solid var(--line); background: var(--panel); }
.nav-group { margin: 0 0 1rem; }
.nav-group h2 { margin: 0 0 .35rem; padding: 0 .8rem; color: var(--muted); font-size: .72rem; letter-spacing: .08em; text-transform: uppercase; }
nav button { width: 100%; border: 0; background: transparent; color: var(--text); text-align: left; padding: .62rem .8rem; margin-bottom: .12rem; border-radius: .5rem; cursor: pointer; font: inherit; }
nav button:hover, nav button.active { background: var(--accent-soft); color: var(--accent); }
main { padding: 1.4rem; min-width: 0; }
aside { padding: 1.2rem; min-width: 0; background: var(--panel); border-left: 1px solid var(--line); }
aside h2 { font-size: 1rem; margin: 0 0 1rem; }
h2 { margin-top: 0; }
h3 { margin-top: 1.4rem; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .8rem; margin: 1rem 0 1.5rem; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; padding: 1rem; }
.card strong { display: block; font-size: 1.65rem; margin-top: .25rem; }
.muted { color: var(--muted); }
.toolbar { display: flex; gap: .65rem; flex-wrap: wrap; margin: .8rem 0 1rem; }
input, select { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: .5rem; padding: .55rem .7rem; font: inherit; }
input[type="search"] { min-width: min(420px, 100%); flex: 1; }
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
.detail dl { display: grid; grid-template-columns: minmax(90px, 120px) 1fr; gap: .45rem .7rem; font-size: .9rem; }
.detail dt { color: var(--muted); }
.detail dd { margin: 0; overflow-wrap: anywhere; }
.detail ul { padding-left: 1.2rem; }
.detail li { margin: .5rem 0; overflow-wrap: anywhere; }
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
.link-button { border: 0; padding: 0; background: transparent; color: var(--accent); cursor: pointer; font: inherit; font-weight: 600; }
details { margin-top: 1rem; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 1050px) {
  .layout { grid-template-columns: 210px minmax(0, 1fr); }
  aside { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--line); }
}
@media (max-width: 700px) {
  .layout { grid-template-columns: 1fr; }
  nav { display: flex; gap: .6rem; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  .nav-group { display: flex; gap: .2rem; margin: 0; }
  .nav-group h2 { align-self: center; white-space: nowrap; }
  nav button { width: auto; white-space: nowrap; }
  aside { grid-column: auto; }
  .detail dl { grid-template-columns: 1fr; }
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
    <p>MBSE Lite · local read-only viewer</p>
  </div>
  <div id="modelCounts" class="muted"></div>
</header>
<div class="layout">
  <nav id="viewNavigation" aria-label="Project views"></nav>
  <main><div id="viewContent"></div></main>
  <aside>
    <h2>Selected object</h2>
    <div id="objectDetail" class="detail muted">Select an object to inspect its attributes and direct relations.</div>
  </aside>
</div>
<script>
const embeddedViewerManifest = __MANIFEST_JSON__;
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
  const attributes = Object.entries(object.attributes)
    .map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join('');
  const relationHtml = direct.length
    ? `<ul>${direct.map(rel => {
        const otherId = rel.source === object.id ? rel.target : rel.source;
        return `<li><span class="badge">${escapeHtml(rel.area)}</span> ${escapeHtml(rel.source)} — ${escapeHtml(rel.relation)} → ${escapeHtml(rel.target)} <button class="link-button" data-object-id="${escapeHtml(otherId)}">select</button></li>`;
      }).join('')}</ul>`
    : '<p class="muted">No direct relations.</p>';
  detail.innerHTML = `
    <h3>${escapeHtml(object.id)} · ${escapeHtml(object.name)}</h3>
    <dl><dt>Area</dt><dd>${escapeHtml(object.area)}</dd><dt>Type</dt><dd>${escapeHtml(object.type)}</dd><dt>Source</dt><dd>${escapeHtml(object.source_file)}</dd>${attributes}</dl>
    <h4>Direct relations</h4>${relationHtml}`;
  detail.querySelectorAll('[data-object-id]').forEach(button =>
    button.addEventListener('click', () => setSelectedObject(button.dataset.objectId)));
}

function setSelectedObject(id) {
  const nextId = id && objects.some(object => object.id === id) ? id : null;
  if (nextId === selectedObjectId) return;
  selectedObjectId = nextId;
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
    host.replaceChildren(renderer.domElement);

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
      container.innerHTML = `${viewHeader(view)}<div class="scaffold gltf-host" data-gltf-host><p class="gltf-status">Loading conceptual 3D view…</p></div>`;
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

async function bootstrapViewer() {
  const snapshot = await embeddedDataProvider.loadProject();
  viewerManifest = snapshot.manifest;
  viewerModel = snapshot.model;
  objects = viewerModel.objects;
  relations = viewerModel.relations;
  supportingTables = viewerModel.tables;
  findings = viewerModel.validation;
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

  window.mbseViewer = {
    getSelectedObjectId: () => selectedObjectId,
    setSelectedObject,
    registerRenderer,
    activateView,
    provider: embeddedDataProvider,
    capabilities: snapshot.capabilities,
    model: viewerModel,
    manifest: viewerManifest
  };

  document.getElementById('modelCounts').textContent = `${viewerModel.summary.objects} objects · ${viewerModel.summary.relations} relations`;
  renderNavigation();
  renderSelectedObject();
  if (viewerManifest.default_view) activateView(viewerManifest.default_view);
  else document.getElementById('viewContent').innerHTML = '<div class="card muted">This viewer manifest contains no views.</div>';
}

bootstrapViewer().catch(error => {
  console.error('The embedded project snapshot could not be loaded.', error);
  document.getElementById('viewContent').innerHTML = '<div class="card muted">The embedded project snapshot could not be loaded.</div>';
});
</script>
</body>
</html>
"""

    replacements = {
        "__TITLE__": title,
        "__MANIFEST_JSON__": _json_for_html(manifest),
        "__MODEL_JSON__": _json_for_html(viewer_model),
        "__ASSETS_JSON__": _json_for_html(embedded_assets),
        "__BINARY_ASSETS_JSON__": _json_for_html(embedded_binary_assets),
        "__ASSET_ERRORS_JSON__": _json_for_html(asset_errors),
        "__THREE_ASSET_PATH__": THREE_ASSET_PATH,
        "__MERMAID_ASSET_PATH__": MERMAID_ASSET_PATH,
    }
    for token, value in replacements.items():
        html = html.replace(token, value)

    output_path.write_text(html, encoding="utf-8")
