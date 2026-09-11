from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .core import Model, mermaid_graph, validate_model


def _json_for_html(value: object) -> str:
    """Serialize data for embedding in an HTML script without closing the script tag."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def export_viewer(
    model: Model,
    output: str | Path,
    *,
    project_name: str = "MBSE Lite Project",
) -> None:
    """Generate a single-file, read-only interactive web viewer for an MBSE Lite model.

    The viewer does not require a Python server. The generated HTML can be opened directly
    in a browser. Mermaid rendering uses a CDN when internet access is available; the rest
    of the viewer remains usable without it.
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    objects = [
        {
            "id": obj.id,
            "type": obj.type,
            "name": obj.attributes.get("Name") or obj.attributes.get("Title") or obj.id,
            "status": obj.attributes.get("Status", ""),
            "source_file": obj.source_file,
            "attributes": obj.attributes,
        }
        for obj in sorted(model.objects.values(), key=lambda item: item.id)
    ]
    relations = [
        {
            "source": rel.source,
            "relation": rel.relation,
            "target": rel.target,
            "source_file": rel.source_file,
        }
        for rel in model.relations
    ]
    findings = [
        {"severity": severity, "message": message}
        for severity, message in validate_model(model)
    ]

    counts: dict[str, int] = {}
    for obj in model.objects.values():
        counts[obj.type] = counts.get(obj.type, 0) + 1

    graph = escape(mermaid_graph(model))
    title = escape(project_name)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · MBSE Lite Viewer</title>
<style>
:root {{
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
}}
@media (prefers-color-scheme: dark) {{
  :root {{
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
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }}
header {{ position: sticky; top: 0; z-index: 10; display: flex; gap: 1rem; align-items: center; justify-content: space-between; padding: 1rem 1.4rem; background: var(--panel); border-bottom: 1px solid var(--line); }}
.brand h1 {{ margin: 0; font-size: 1.15rem; }}
.brand p {{ margin: .2rem 0 0; color: var(--muted); font-size: .85rem; }}
.layout {{ display: grid; grid-template-columns: 220px minmax(0, 1fr); min-height: calc(100vh - 74px); }}
nav {{ padding: 1rem; border-right: 1px solid var(--line); background: var(--panel); }}
nav button {{ width: 100%; border: 0; background: transparent; color: var(--text); text-align: left; padding: .7rem .8rem; margin-bottom: .2rem; border-radius: .5rem; cursor: pointer; font: inherit; }}
nav button:hover, nav button.active {{ background: var(--accent-soft); color: var(--accent); }}
main {{ padding: 1.4rem; min-width: 0; }}
section {{ display: none; }}
section.active {{ display: block; }}
h2 {{ margin-top: 0; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .8rem; margin: 1rem 0 1.5rem; }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; padding: 1rem; }}
.card strong {{ display: block; font-size: 1.65rem; margin-top: .25rem; }}
.muted {{ color: var(--muted); }}
.toolbar {{ display: flex; gap: .65rem; flex-wrap: wrap; margin: .8rem 0 1rem; }}
input, select {{ border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: .5rem; padding: .55rem .7rem; font: inherit; }}
input[type="search"] {{ min-width: min(420px, 100%); flex: 1; }}
.table-wrap {{ overflow: auto; background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: .92rem; }}
th, td {{ padding: .6rem .75rem; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
th {{ position: sticky; top: 0; background: var(--panel); color: var(--muted); font-weight: 600; }}
tbody tr:hover {{ background: var(--accent-soft); }}
tbody tr.object-row {{ cursor: pointer; }}
.badge {{ display: inline-block; border: 1px solid var(--line); border-radius: 99px; padding: .12rem .5rem; font-size: .78rem; white-space: nowrap; }}
.severity-ERROR {{ color: var(--error); font-weight: 700; }}
.severity-WARNING {{ color: var(--warn); font-weight: 700; }}
.severity-OK {{ color: var(--ok); font-weight: 700; }}
.detail {{ margin-top: 1rem; background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; padding: 1rem; }}
.detail dl {{ display: grid; grid-template-columns: minmax(120px, 180px) 1fr; gap: .45rem .8rem; }}
.detail dt {{ color: var(--muted); }}
.detail dd {{ margin: 0; overflow-wrap: anywhere; }}
.graph {{ background: var(--panel); border: 1px solid var(--line); border-radius: .7rem; padding: 1rem; overflow: auto; }}
details {{ margin-top: 1rem; }}
pre {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
@media (max-width: 760px) {{
  .layout {{ grid-template-columns: 1fr; }}
  nav {{ display: flex; gap: .3rem; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--line); }}
  nav button {{ width: auto; white-space: nowrap; }}
  .detail dl {{ grid-template-columns: 1fr; }}
}}
</style>
<script type="module">
try {{
  const mermaid = (await import('https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs')).default;
  mermaid.initialize({{ startOnLoad: true, securityLevel: 'strict' }});
}} catch (error) {{
  console.info('Mermaid could not be loaded. The viewer remains usable without graph rendering.', error);
}}
</script>
</head>
<body>
<header>
  <div class="brand">
    <h1>{title}</h1>
    <p>MBSE Lite · local read-only viewer</p>
  </div>
  <div class="muted">{len(objects)} objects · {len(relations)} relations</div>
</header>
<div class="layout">
<nav aria-label="Viewer sections">
  <button class="active" data-section="overview">Overview</button>
  <button data-section="objects">Objects</button>
  <button data-section="relations">Relations</button>
  <button data-section="validation">Validation</button>
  <button data-section="traceability">Traceability</button>
</nav>
<main>
<section id="overview" class="active">
  <h2>Overview</h2>
  <p class="muted">Summary of the Markdown source-of-truth model.</p>
  <div class="cards" id="countCards"></div>
  <div class="cards">
    <div class="card"><span class="muted">Relations</span><strong>{len(relations)}</strong></div>
    <div class="card"><span class="muted">Validation findings</span><strong>{len(findings)}</strong></div>
  </div>
</section>
<section id="objects">
  <h2>Objects</h2>
  <div class="toolbar">
    <input id="objectSearch" type="search" placeholder="Search ID, name, status, attributes…">
    <select id="typeFilter"><option value="">All object types</option></select>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>ID</th><th>Type</th><th>Name</th><th>Status</th><th>Source</th></tr></thead>
      <tbody id="objectRows"></tbody>
    </table>
  </div>
  <div id="objectDetail" class="detail muted">Select an object to inspect all attributes and its direct relations.</div>
</section>
<section id="relations">
  <h2>Relations</h2>
  <div class="toolbar"><input id="relationSearch" type="search" placeholder="Search source, relation or target…"></div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>Source</th><th>Relation</th><th>Target</th><th>Source file</th></tr></thead>
      <tbody id="relationRows"></tbody>
    </table>
  </div>
</section>
<section id="validation">
  <h2>Validation</h2>
  <div id="validationContent"></div>
</section>
<section id="traceability">
  <h2>Traceability</h2>
  <p class="muted">The graph uses Mermaid from a CDN. If the notebook is offline, use the object and relation views or inspect the graph source below.</p>
  <div class="graph"><pre class="mermaid">{graph}</pre></div>
  <details><summary>Mermaid source</summary><pre>{graph}</pre></details>
</section>
</main>
</div>
<script>
const objects = {_json_for_html(objects)};
const relations = {_json_for_html(relations)};
const findings = {_json_for_html(findings)};
const counts = {_json_for_html(counts)};

const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

function showSection(id) {{
  document.querySelectorAll('main section').forEach(section => section.classList.toggle('active', section.id === id));
  document.querySelectorAll('nav button').forEach(button => button.classList.toggle('active', button.dataset.section === id));
}}
document.querySelectorAll('nav button').forEach(button => button.addEventListener('click', () => showSection(button.dataset.section)));

const countCards = document.getElementById('countCards');
Object.entries(counts).sort(([a], [b]) => a.localeCompare(b)).forEach(([type, count]) => {{
  countCards.insertAdjacentHTML('beforeend', `<div class="card"><span class="muted">${{escapeHtml(type)}}</span><strong>${{count}}</strong></div>`);
}});

const typeFilter = document.getElementById('typeFilter');
[...new Set(objects.map(object => object.type))].sort().forEach(type => {{
  const option = document.createElement('option');
  option.value = type;
  option.textContent = type;
  typeFilter.appendChild(option);
}});

function renderObjects() {{
  const query = document.getElementById('objectSearch').value.trim().toLowerCase();
  const type = typeFilter.value;
  const rows = objects.filter(object => {{
    const searchable = JSON.stringify(object).toLowerCase();
    return (!type || object.type === type) && (!query || searchable.includes(query));
  }});
  document.getElementById('objectRows').innerHTML = rows.map(object => `
    <tr class="object-row" data-id="${{escapeHtml(object.id)}}">
      <td><strong>${{escapeHtml(object.id)}}</strong></td>
      <td><span class="badge">${{escapeHtml(object.type)}}</span></td>
      <td>${{escapeHtml(object.name)}}</td>
      <td>${{escapeHtml(object.status)}}</td>
      <td>${{escapeHtml(object.source_file)}}</td>
    </tr>`).join('');
  document.querySelectorAll('.object-row').forEach(row => row.addEventListener('click', () => showObject(row.dataset.id)));
}}

function showObject(id) {{
  const object = objects.find(item => item.id === id);
  if (!object) return;
  const direct = relations.filter(rel => rel.source === id || rel.target === id);
  const attributes = Object.entries(object.attributes).map(([key, value]) => `<dt>${{escapeHtml(key)}}</dt><dd>${{escapeHtml(value)}}</dd>`).join('');
  const relHtml = direct.length
    ? `<ul>${{direct.map(rel => `<li><strong>${{escapeHtml(rel.source)}}</strong> — ${{escapeHtml(rel.relation)}} → <strong>${{escapeHtml(rel.target)}}</strong></li>`).join('')}}</ul>`
    : '<p class="muted">No direct relations.</p>';
  document.getElementById('objectDetail').innerHTML = `
    <h3>${{escapeHtml(object.id)}} · ${{escapeHtml(object.name)}}</h3>
    <dl><dt>Type</dt><dd>${{escapeHtml(object.type)}}</dd><dt>Source</dt><dd>${{escapeHtml(object.source_file)}}</dd>${{attributes}}</dl>
    <h4>Direct relations</h4>${{relHtml}}`;
}}

document.getElementById('objectSearch').addEventListener('input', renderObjects);
typeFilter.addEventListener('change', renderObjects);
renderObjects();

function renderRelations() {{
  const query = document.getElementById('relationSearch').value.trim().toLowerCase();
  const rows = relations.filter(rel => !query || JSON.stringify(rel).toLowerCase().includes(query));
  document.getElementById('relationRows').innerHTML = rows.map(rel => `
    <tr><td>${{escapeHtml(rel.source)}}</td><td>${{escapeHtml(rel.relation)}}</td><td>${{escapeHtml(rel.target)}}</td><td>${{escapeHtml(rel.source_file)}}</td></tr>`).join('');
}}
document.getElementById('relationSearch').addEventListener('input', renderRelations);
renderRelations();

const validationContent = document.getElementById('validationContent');
if (!findings.length) {{
  validationContent.innerHTML = '<div class="card"><span class="severity-OK">OK</span> · No validation findings.</div>';
}} else {{
  validationContent.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Severity</th><th>Finding</th></tr></thead><tbody>${{findings.map(item => `<tr><td class="severity-${{escapeHtml(item.severity)}}">${{escapeHtml(item.severity)}}</td><td>${{escapeHtml(item.message)}}</td></tr>`).join('')}}</tbody></table></div>`;
}}
</script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")
