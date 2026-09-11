from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .core import Model, Relation, validate_model


MBSE_AREA = "MBSE"
PROJECT_MANAGEMENT_AREA = "Project Management"
PM_RELATION_AREA = "Project Management / Cross-area"


def _json_for_html(value: object) -> str:
    """Serialize data for embedding in an HTML script without closing the script tag."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _area_for_source(source_file: str, object_type: str = "") -> str:
    normalized = source_file.replace("\\", "/")
    file_name = Path(normalized).name.lower()
    if normalized.startswith("project_management/") or "project_management" in file_name:
        return PROJECT_MANAGEMENT_AREA
    if object_type in {"Task", "Milestone"}:
        return PROJECT_MANAGEMENT_AREA
    return MBSE_AREA


def _mermaid_subset(model: Model, object_ids: set[str], relations: list[Relation]) -> str:
    lines = ["flowchart LR"]
    for object_id in sorted(object_ids):
        obj = model.objects.get(object_id)
        if obj is None:
            continue
        label = obj.attributes.get("Name") or obj.attributes.get("Title") or obj.id
        safe_label = label.replace('"', "'")
        lines.append(f'    {obj.id.replace("-", "_")}["{obj.id}<br/>{safe_label}"]')
    for rel in relations:
        if rel.source in object_ids and rel.target in object_ids:
            lines.append(
                f'    {rel.source.replace("-", "_")} -->|{rel.relation}| {rel.target.replace("-", "_")}'
            )
    return "\n".join(lines)


def export_viewer(
    model: Model,
    output: str | Path,
    *,
    project_name: str = "MBSE Lite Project",
) -> None:
    """Generate a single-file, read-only interactive web viewer for an MBSE Lite model."""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    object_areas: dict[str, str] = {}
    objects = []
    for obj in sorted(model.objects.values(), key=lambda item: item.id):
        area = _area_for_source(obj.source_file, obj.type)
        object_areas[obj.id] = area
        objects.append(
            {
                "id": obj.id,
                "type": obj.type,
                "area": area,
                "name": obj.attributes.get("Name") or obj.attributes.get("Title") or obj.id,
                "status": obj.attributes.get("Status", ""),
                "source_file": obj.source_file,
                "attributes": obj.attributes,
            }
        )

    relations = []
    for rel in model.relations:
        source_area = object_areas.get(rel.source, _area_for_source(rel.source_file))
        target_area = object_areas.get(rel.target, source_area)
        area = (
            PM_RELATION_AREA
            if PROJECT_MANAGEMENT_AREA in {source_area, target_area}
            else MBSE_AREA
        )
        relations.append(
            {
                "source": rel.source,
                "relation": rel.relation,
                "target": rel.target,
                "source_file": rel.source_file,
                "area": area,
            }
        )

    findings = [
        {"severity": severity, "message": message}
        for severity, message in validate_model(model)
    ]

    supporting_tables = []
    for key, rows in sorted(model.tables.items()):
        if not rows:
            continue
        headers = list(rows[0])
        header_set = set(headers)
        if "ID" in header_set or {"Source", "Relation", "Target"}.issubset(header_set):
            continue
        source_file = key.rsplit(":", 1)[0]
        supporting_tables.append(
            {
                "source_file": source_file,
                "area": _area_for_source(source_file),
                "headers": headers,
                "rows": [[row.get(header, "") for header in headers] for row in rows],
            }
        )

    mbse_ids = {object_id for object_id, area in object_areas.items() if area == MBSE_AREA}
    pm_ids = {object_id for object_id, area in object_areas.items() if area == PROJECT_MANAGEMENT_AREA}

    mbse_relations = [
        rel for rel in model.relations if rel.source in mbse_ids and rel.target in mbse_ids
    ]
    delivery_relations = [
        rel for rel in model.relations if rel.source in pm_ids or rel.target in pm_ids
    ]
    delivery_ids = set(pm_ids)
    for rel in delivery_relations:
        delivery_ids.add(rel.source)
        delivery_ids.add(rel.target)

    mbse_graph = escape(_mermaid_subset(model, mbse_ids, mbse_relations))
    delivery_graph = escape(_mermaid_subset(model, delivery_ids, delivery_relations))
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
.layout { display: grid; grid-template-columns: 230px minmax(0, 1fr); min-height: calc(100vh - 74px); }
nav { padding: 1rem; border-right: 1px solid var(--line); background: var(--panel); }
nav button { width: 100%; border: 0; background: transparent; color: var(--text); text-align: left; padding: .7rem .8rem; margin-bottom: .2rem; border-radius: .5rem; cursor: pointer; font: inherit; }
nav button:hover, nav button.active { background: var(--accent-soft); color: var(--accent); }
main { padding: 1.4rem; min-width: 0; }
section { display: none; }
section.active { display: block; }
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
tbody tr:hover { background: var(--accent-soft); }
tbody tr.object-row { cursor: pointer; }
.badge { display: inline-block; border: 1px solid var(--line); border-radius: 99px; padding: .12rem .5rem; font-size: .78rem; white-space: nowrap; }
.severity-ERROR { color: var(--error); font-weight: 700; }
.severity-WARNING { color: var(--warn); font-weight: 700; }
.severity-OK { color: var(--ok); font-weight: 700; }
.detail { margin-top: 1rem; background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; padding: 1rem; }
.detail dl { display: grid; grid-template-columns: minmax(120px, 180px) 1fr; gap: .45rem .8rem; }
.detail dt { color: var(--muted); }
.detail dd { margin: 0; overflow-wrap: anywhere; }
.graph { background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; padding: 1rem; overflow: auto; margin-bottom: 1rem; }
.data-block { margin: 1rem 0 1.4rem; }
.data-block h3 { margin-bottom: .35rem; }
details { margin-top: 1rem; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 760px) {
  .layout { grid-template-columns: 1fr; }
  nav { display: flex; gap: .3rem; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  nav button { width: auto; white-space: nowrap; }
  .detail dl { grid-template-columns: 1fr; }
}
</style>
<script type="module">
try {
  const mermaid = (await import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs')).default;
  mermaid.initialize({ startOnLoad: true, securityLevel: 'strict' });
} catch (error) {
  console.info('Mermaid could not be loaded. The viewer remains usable without graph rendering.', error);
}
</script>
</head>
<body>
<header>
  <div class="brand">
    <h1>__TITLE__</h1>
    <p>MBSE Lite · local read-only viewer</p>
  </div>
  <div class="muted">__OBJECT_COUNT__ objects · __RELATION_COUNT__ relations</div>
</header>
<div class="layout">
<nav aria-label="Viewer sections">
  <button class="active" data-section="overview">Overview</button>
  <button data-section="mbse">MBSE</button>
  <button data-section="projectManagement">Project Management</button>
  <button data-section="projectData">Project Data</button>
  <button data-section="relations">Relations</button>
  <button data-section="validation">Validation</button>
  <button data-section="traceability">Traceability</button>
</nav>
<main>
<section id="overview" class="active">
  <h2>Overview</h2>
  <p class="muted">Engineering definition and project execution are intentionally presented as separate areas of one traceable project.</p>
  <div class="cards">
    <div class="card"><span class="muted">MBSE objects</span><strong>__MBSE_COUNT__</strong></div>
    <div class="card"><span class="muted">Project-management objects</span><strong>__PM_COUNT__</strong></div>
    <div class="card"><span class="muted">Relations</span><strong>__RELATION_COUNT__</strong></div>
    <div class="card"><span class="muted">Supporting data tables</span><strong>__DATA_TABLE_COUNT__</strong></div>
    <div class="card"><span class="muted">Validation findings</span><strong>__FINDING_COUNT__</strong></div>
  </div>
</section>
<section id="mbse">
  <h2>MBSE</h2>
  <p class="muted">Needs, requirements, functions, architecture, concepts, technical decisions, verification and engineering issues/risks.</p>
  <div class="toolbar">
    <input id="mbseSearch" type="search" placeholder="Search engineering objects…">
    <select id="mbseTypeFilter"><option value="">All MBSE object types</option></select>
  </div>
  <div class="table-wrap"><table><thead><tr><th>ID</th><th>Type</th><th>Name</th><th>Status</th><th>Source</th></tr></thead><tbody id="mbseRows"></tbody></table></div>
  <div id="mbseDetail" class="detail muted">Select an engineering object to inspect attributes and direct relations.</div>
</section>
<section id="projectManagement">
  <h2>Project Management</h2>
  <p class="muted">Tasks, milestones and execution-oriented objects. Engineering facts remain in the MBSE area.</p>
  <div class="toolbar">
    <input id="pmSearch" type="search" placeholder="Search project-management objects…">
    <select id="pmTypeFilter"><option value="">All project-management object types</option></select>
  </div>
  <div class="table-wrap"><table><thead><tr><th>ID</th><th>Type</th><th>Name</th><th>Status</th><th>Source</th></tr></thead><tbody id="pmRows"></tbody></table></div>
  <div id="pmDetail" class="detail muted">Select a project-management object to inspect attributes and direct relations.</div>
</section>
<section id="projectData">
  <h2>Project Data</h2>
  <p class="muted">Supporting Markdown tables that are not MBSE objects or relation tables, for example inventory or site data.</p>
  <div class="toolbar"><input id="dataSearch" type="search" placeholder="Search supporting project data…"></div>
  <div id="dataContent"></div>
</section>
<section id="relations">
  <h2>Relations</h2>
  <div class="toolbar">
    <input id="relationSearch" type="search" placeholder="Search source, relation or target…">
    <select id="relationAreaFilter"><option value="">All relation areas</option><option value="MBSE">MBSE</option><option value="Project Management / Cross-area">Project Management / Cross-area</option></select>
  </div>
  <div class="table-wrap"><table><thead><tr><th>Area</th><th>Source</th><th>Relation</th><th>Target</th><th>Source file</th></tr></thead><tbody id="relationRows"></tbody></table></div>
</section>
<section id="validation">
  <h2>Validation</h2>
  <div id="validationContent"></div>
</section>
<section id="traceability">
  <h2>Traceability</h2>
  <p class="muted">Engineering traceability is separated from work-to-engineering delivery links.</p>
  <h3>MBSE traceability</h3>
  <div class="graph"><pre class="mermaid">__MBSE_GRAPH__</pre></div>
  <details><summary>MBSE Mermaid source</summary><pre>__MBSE_GRAPH__</pre></details>
  <h3>Project-management / cross-area traceability</h3>
  <div class="graph"><pre class="mermaid">__DELIVERY_GRAPH__</pre></div>
  <details><summary>Project-management Mermaid source</summary><pre>__DELIVERY_GRAPH__</pre></details>
</section>
</main>
</div>
<script>
const objects = __OBJECTS_JSON__;
const relations = __RELATIONS_JSON__;
const findings = __FINDINGS_JSON__;
const supportingTables = __TABLES_JSON__;

const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

function showSection(id) {
  document.querySelectorAll('main section').forEach(section => section.classList.toggle('active', section.id === id));
  document.querySelectorAll('nav button').forEach(button => button.classList.toggle('active', button.dataset.section === id));
}
document.querySelectorAll('nav button').forEach(button => button.addEventListener('click', () => showSection(button.dataset.section)));

function showObject(id, detailId) {
  const object = objects.find(item => item.id === id);
  if (!object) return;
  const direct = relations.filter(rel => rel.source === id || rel.target === id);
  const attributes = Object.entries(object.attributes).map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join('');
  const relHtml = direct.length
    ? `<ul>${direct.map(rel => `<li><span class="badge">${escapeHtml(rel.area)}</span> <strong>${escapeHtml(rel.source)}</strong> — ${escapeHtml(rel.relation)} → <strong>${escapeHtml(rel.target)}</strong></li>`).join('')}</ul>`
    : '<p class="muted">No direct relations.</p>';
  document.getElementById(detailId).innerHTML = `
    <h3>${escapeHtml(object.id)} · ${escapeHtml(object.name)}</h3>
    <dl><dt>Area</dt><dd>${escapeHtml(object.area)}</dd><dt>Type</dt><dd>${escapeHtml(object.type)}</dd><dt>Source</dt><dd>${escapeHtml(object.source_file)}</dd>${attributes}</dl>
    <h4>Direct relations</h4>${relHtml}`;
}

function setupObjectArea(area, prefix) {
  const search = document.getElementById(`${prefix}Search`);
  const typeFilter = document.getElementById(`${prefix}TypeFilter`);
  const rowsElement = document.getElementById(`${prefix}Rows`);
  const detailId = `${prefix}Detail`;
  const areaObjects = objects.filter(object => object.area === area);

  [...new Set(areaObjects.map(object => object.type))].sort().forEach(type => {
    const option = document.createElement('option');
    option.value = type;
    option.textContent = type;
    typeFilter.appendChild(option);
  });

  function render() {
    const query = search.value.trim().toLowerCase();
    const type = typeFilter.value;
    const rows = areaObjects.filter(object => {
      const searchable = JSON.stringify(object).toLowerCase();
      return (!type || object.type === type) && (!query || searchable.includes(query));
    });
    rowsElement.innerHTML = rows.map(object => `
      <tr class="object-row" data-id="${escapeHtml(object.id)}">
        <td><strong>${escapeHtml(object.id)}</strong></td>
        <td><span class="badge">${escapeHtml(object.type)}</span></td>
        <td>${escapeHtml(object.name)}</td>
        <td>${escapeHtml(object.status)}</td>
        <td>${escapeHtml(object.source_file)}</td>
      </tr>`).join('');
    rowsElement.querySelectorAll('.object-row').forEach(row => row.addEventListener('click', () => showObject(row.dataset.id, detailId)));
  }

  search.addEventListener('input', render);
  typeFilter.addEventListener('change', render);
  render();
}

setupObjectArea('MBSE', 'mbse');
setupObjectArea('Project Management', 'pm');

function renderProjectData() {
  const query = document.getElementById('dataSearch').value.trim().toLowerCase();
  const tables = supportingTables.filter(table => !query || JSON.stringify(table).toLowerCase().includes(query));
  const container = document.getElementById('dataContent');
  if (!tables.length) {
    container.innerHTML = '<div class="card muted">No supporting data tables match the current filter.</div>';
    return;
  }
  container.innerHTML = tables.map(table => {
    const headers = table.headers.map(header => `<th>${escapeHtml(header)}</th>`).join('');
    const rows = table.rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`).join('');
    return `<div class="data-block"><h3>${escapeHtml(table.source_file)}</h3><span class="badge">${escapeHtml(table.area)}</span><div class="table-wrap"><table><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table></div></div>`;
  }).join('');
}
document.getElementById('dataSearch').addEventListener('input', renderProjectData);
renderProjectData();

function renderRelations() {
  const query = document.getElementById('relationSearch').value.trim().toLowerCase();
  const area = document.getElementById('relationAreaFilter').value;
  const rows = relations.filter(rel => (!area || rel.area === area) && (!query || JSON.stringify(rel).toLowerCase().includes(query)));
  document.getElementById('relationRows').innerHTML = rows.map(rel => `
    <tr><td><span class="badge">${escapeHtml(rel.area)}</span></td><td>${escapeHtml(rel.source)}</td><td>${escapeHtml(rel.relation)}</td><td>${escapeHtml(rel.target)}</td><td>${escapeHtml(rel.source_file)}</td></tr>`).join('');
}
document.getElementById('relationSearch').addEventListener('input', renderRelations);
document.getElementById('relationAreaFilter').addEventListener('change', renderRelations);
renderRelations();

const validationContent = document.getElementById('validationContent');
if (!findings.length) {
  validationContent.innerHTML = '<div class="card"><span class="severity-OK">OK</span> · No validation findings.</div>';
} else {
  validationContent.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Severity</th><th>Finding</th></tr></thead><tbody>${findings.map(item => `<tr><td class="severity-${escapeHtml(item.severity)}">${escapeHtml(item.severity)}</td><td>${escapeHtml(item.message)}</td></tr>`).join('')}</tbody></table></div>`;
}
</script>
</body>
</html>
"""

    replacements = {
        "__TITLE__": title,
        "__OBJECT_COUNT__": str(len(objects)),
        "__RELATION_COUNT__": str(len(relations)),
        "__MBSE_COUNT__": str(len(mbse_ids)),
        "__PM_COUNT__": str(len(pm_ids)),
        "__DATA_TABLE_COUNT__": str(len(supporting_tables)),
        "__FINDING_COUNT__": str(len(findings)),
        "__OBJECTS_JSON__": _json_for_html(objects),
        "__RELATIONS_JSON__": _json_for_html(relations),
        "__FINDINGS_JSON__": _json_for_html(findings),
        "__TABLES_JSON__": _json_for_html(supporting_tables),
        "__MBSE_GRAPH__": mbse_graph,
        "__DELIVERY_GRAPH__": delivery_graph,
    }
    for token, value in replacements.items():
        html = html.replace(token, value)

    output_path.write_text(html, encoding="utf-8")
