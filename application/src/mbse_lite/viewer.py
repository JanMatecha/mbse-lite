from __future__ import annotations

import json
from html import escape
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from .core import Model
from .view_architecture import (
    ViewDefinition,
    build_default_view_assets,
    build_viewer_manifest,
    build_viewer_model,
)


def _json_for_html(value: object) -> str:
    """Serialize data for a script block without allowing an early script close."""

    return (
        json.dumps(value, ensure_ascii=False)
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _asset_output_path(output_dir: Path, source: str) -> Path:
    normalized = source.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if (
        not normalized
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or ":" in relative.parts[0]
    ):
        raise ValueError(f"View asset path must be a safe relative path: {source!r}")
    return output_dir.joinpath(*relative.parts)


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
    assets. Text assets are embedded in the HTML so the viewer still works when
    opened directly through ``file://``.
    """

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    viewer_model = build_viewer_model(model)
    manifest = build_viewer_manifest(project_name, views)
    assets: dict[str, str | bytes] = {}
    if views is None:
        assets.update(build_default_view_assets(model))
    if view_assets:
        assets.update(view_assets)

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
<script type="module">
window.mbseMermaidReady = (async () => {
  try {
    const mermaid = (await import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs')).default;
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict' });
    return mermaid;
  } catch (error) {
    console.info('Mermaid could not be loaded. Source remains available.', error);
    return null;
  }
})();
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
const viewerManifest = __MANIFEST_JSON__;
const viewerModel = __MODEL_JSON__;
const embeddedViewAssets = __ASSETS_JSON__;

const objects = viewerModel.objects;
const relations = viewerModel.relations;
const supportingTables = viewerModel.tables;
const findings = viewerModel.validation;

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
  return {
    mount(container) {
      const source = context.assets[view.source];
      if (typeof source !== 'string') {
        container.innerHTML = `${viewHeader(view)}<div class="scaffold muted">Mermaid source is unavailable: ${escapeHtml(view.source || '(no source)')}</div>`;
        return;
      }
      container.innerHTML = `${viewHeader(view)}<div class="graph"><pre class="mermaid">${escapeHtml(source)}</pre></div><details><summary>Mermaid source</summary><pre>${escapeHtml(source)}</pre></details>`;
      const graph = container.querySelector('.mermaid');
      window.mbseMermaidReady?.then(mermaid => mermaid?.run({ nodes: [graph] }));
    },
    onSelectionChanged(id) {
      this.selectedObjectId = id;
    }
  };
}

function safeAssetSource(source) {
  const normalized = String(source || '').replaceAll('\\\\', '/');
  if (!normalized || normalized.startsWith('/') || normalized.startsWith('//') || /^[a-z][a-z0-9+.-]*:/i.test(normalized)) return null;
  if (normalized.split('/').some(part => !part || part === '.' || part === '..')) return null;
  return normalized;
}

function svgRenderer(view) {
  let selectionNote;
  return {
    mount(container) {
      const source = safeAssetSource(view.source);
      container.innerHTML = `${viewHeader(view)}<div class="scaffold" data-svg-host></div>`;
      const host = container.querySelector('[data-svg-host]');
      if (!source) {
        host.innerHTML = '<p class="muted">SVG source is missing or unsafe.</p>';
        return;
      }
      const image = document.createElement('img');
      image.className = 'engineering-asset';
      image.src = source;
      image.alt = view.title;
      host.appendChild(image);
      selectionNote = document.createElement('p');
      selectionNote.className = 'muted';
      selectionNote.textContent = 'SVG identity convention: data-mbse-id on source elements. Selection highlighting is reserved for a later renderer revision.';
      host.appendChild(selectionNote);
    },
    onSelectionChanged(id) {
      if (selectionNote) selectionNote.dataset.selectedObjectId = id || '';
    }
  };
}

function scaffoldRenderer(kind) {
  let selectionValue;
  return (view) => ({
    mount(container) {
      container.innerHTML = `${viewHeader(view)}<div class="scaffold"><p><strong>${escapeHtml(kind)} renderer contract is available; interactive rendering is not implemented in V0.1.</strong></p><p class="muted">Source: ${escapeHtml(view.source || '(not specified)')}</p><p class="muted" data-selection-value>No object selected.</p></div>`;
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
  gltf: scaffoldRenderer('glTF')
};

const viewerContext = {
  model: viewerModel,
  manifest: viewerManifest,
  assets: embeddedViewAssets,
  setSelectedObject,
  getSelectedObjectId: () => selectedObjectId
};

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

window.mbseViewer = {
  getSelectedObjectId: () => selectedObjectId,
  setSelectedObject,
  registerRenderer,
  activateView,
  model: viewerModel,
  manifest: viewerManifest
};

document.getElementById('modelCounts').textContent = `${viewerModel.summary.objects} objects · ${viewerModel.summary.relations} relations`;
renderNavigation();
renderSelectedObject();
if (viewerManifest.default_view) activateView(viewerManifest.default_view);
else document.getElementById('viewContent').innerHTML = '<div class="card muted">This viewer manifest contains no views.</div>';
</script>
</body>
</html>
"""

    replacements = {
        "__TITLE__": title,
        "__MANIFEST_JSON__": _json_for_html(manifest),
        "__MODEL_JSON__": _json_for_html(viewer_model),
        "__ASSETS_JSON__": _json_for_html(embedded_assets),
    }
    for token, value in replacements.items():
        html = html.replace(token, value)

    output_path.write_text(html, encoding="utf-8")
