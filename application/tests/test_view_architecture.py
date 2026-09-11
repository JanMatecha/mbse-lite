import json
from pathlib import Path
from xml.etree import ElementTree

import pytest

from mbse_lite.core import Model, ModelObject, load_model
from mbse_lite.view_architecture import (
    MBSE_AREA,
    PROJECT_MANAGEMENT_AREA,
    SUPPORTED_VIEW_TYPES,
    ViewDefinition,
    build_viewer_manifest,
)
from mbse_lite.viewer import export_viewer


def demo_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "demo_project"


def garden_shed_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "garden_tool_shed"


def test_default_manifest_defines_grouped_navigation_and_asset_views():
    manifest = build_viewer_manifest("demo_project")

    assert manifest["schema_version"] == "0.2"
    assert manifest["project"] == "demo_project"
    assert manifest["default_view"] == "overview"
    assert [view["id"] for view in manifest["views"]] == [
        "overview",
        "mbse",
        "traceability",
        "project-data",
        "relations",
        "project-management",
        "delivery-traceability",
        "validation",
    ]
    assert {view["group"] for view in manifest["views"]} == {
        "System",
        "Data",
        "Project",
        "Quality",
    }
    assert {"mermaid", "graph", "svg", "gltf"}.issubset(SUPPORTED_VIEW_TYPES)


def test_viewer_bundle_contains_manifest_model_and_meaningful_view_assets(tmp_path):
    output = tmp_path / "index.html"

    export_viewer(load_model(demo_project()), output, project_name="Demo Project")

    manifest = json.loads((tmp_path / "viewer.json").read_text(encoding="utf-8"))
    generated_model = json.loads((tmp_path / "model.json").read_text(encoding="utf-8"))
    html = output.read_text(encoding="utf-8")

    assert manifest["project"] == "Demo Project"
    assert any(view["source"] == "views/traceability.mmd" for view in manifest["views"] if "source" in view)
    assert (tmp_path / "views" / "traceability.mmd").read_text(encoding="utf-8").startswith("flowchart LR")
    assert (tmp_path / "views" / "delivery-traceability.mmd").exists()
    assert {item["id"] for item in generated_model["objects"]}.issuperset({"NEED-001", "TASK-001"})
    assert any(item["area"] == MBSE_AREA for item in generated_model["objects"])
    assert any(item["area"] == PROJECT_MANAGEMENT_AREA for item in generated_model["objects"])
    assert "renderNavigation" in html
    assert "viewerManifest.views" in html
    assert "let selectedObjectId = null" in html
    assert "onSelectionChanged" in html


def test_garden_shed_bundle_contains_interactive_floor_plan_with_model_ids(tmp_path):
    model = load_model(garden_shed_project())
    output = tmp_path / "index.html"

    export_viewer(model, output, project_name="garden_tool_shed")

    manifest = json.loads((tmp_path / "viewer.json").read_text(encoding="utf-8"))
    floor_plan = next(view for view in manifest["views"] if view["id"] == "floor-plan")
    svg_text = (tmp_path / "views" / "floorplan.svg").read_text(encoding="utf-8")
    svg = ElementTree.fromstring(svg_text)
    mapped_ids = {
        element.attrib["data-mbse-id"]
        for element in svg.iter()
        if "data-mbse-id" in element.attrib
    }

    assert floor_plan == {
        "id": "floor-plan",
        "title": "Floor Plan",
        "group": "Geometry",
        "type": "svg",
        "source": "views/floorplan.svg",
        "description": (
            "Conceptual 2D layout derived from modeled parts. Approximate envelope data may set "
            "the aspect ratio; unresolved internal geometry remains visualization-only."
        ),
        "config": {
            "geometry_status": "conceptual",
            "not_to_scale_where_tbd": True,
            "displayed_candidates": ["CON-007", "CON-010"],
        },
    }
    assert mapped_ids == {
        "PART-001",
        "PART-004",
        "PART-005",
        "PART-008",
        "PART-010",
        "PART-011",
        "PART-012",
    }
    assert mapped_ids <= set(model.objects)
    assert "4.0 m × 1.2 m from REQ-008" in svg_text
    assert "visualization-only" in svg_text
    assert "Preferred candidates shown: CON-007, CON-010" in svg_text


def test_svg_renderer_uses_embedded_dom_and_shared_selection_contract(tmp_path):
    output = tmp_path / "index.html"
    export_viewer(load_model(garden_shed_project()), output, project_name="garden_tool_shed")

    html = output.read_text(encoding="utf-8")

    assert "const svgSource = context.assets[source]" in html
    assert "new DOMParser().parseFromString(source, 'image/svg+xml')" in html
    assert "event.target.closest?.('[data-mbse-id]')" in html
    assert "context.setSelectedObject(element.getAttribute('data-mbse-id'))" in html
    assert "element.classList.toggle('mbse-selected'" in html
    assert "image.src = source" not in html


def test_svg_is_sanitized_before_file_and_html_emission(tmp_path):
    malicious_svg = """<svg xmlns="http://www.w3.org/2000/svg" onload="alert(0)">
      <script id="svg-attack">alert(1)</script>
      <rect data-mbse-id="PART-001" onclick="alert(2)" width="10" height="10"/>
      <a href="javascript:alert(3)"><text>unsafe link</text></a>
      <image href="https://example.invalid/tracker.png"/>
    </svg>"""
    view = ViewDefinition(
        id="security-svg",
        title="Security SVG",
        group="Test",
        type="svg",
        source="views/security.svg",
    )
    output = tmp_path / "index.html"

    export_viewer(
        Model(),
        output,
        project_name="Security",
        views=[view],
        view_assets={"views/security.svg": malicious_svg},
    )

    emitted_svg = (tmp_path / "views" / "security.svg").read_text(encoding="utf-8")
    html = output.read_text(encoding="utf-8")
    assert "svg-attack" not in emitted_svg
    assert "alert(1)" not in emitted_svg
    assert "onclick=" not in emitted_svg
    assert "javascript:alert(3)" not in emitted_svg
    assert "tracker.png" not in emitted_svg
    assert "svg-attack" not in html
    assert "alert(1)" not in html
    assert "onclick=\"alert(2)\"" not in html
    assert "javascript:alert(3)" not in html


def test_unknown_view_type_is_preserved_for_graceful_browser_fallback(tmp_path):
    view = ViewDefinition(
        id="future-view",
        title="Future View",
        group="Experimental",
        type="not-installed",
    )
    output = tmp_path / "index.html"

    export_viewer(Model(), output, project_name="Future", views=[view])

    manifest = json.loads((tmp_path / "viewer.json").read_text(encoding="utf-8"))
    html = output.read_text(encoding="utf-8")
    assert manifest["views"][0]["type"] == "not-installed"
    assert "rendererFactories[view.type] || unsupportedRenderer" in html
    assert "Unsupported view type" in html


def test_html_embedding_escapes_script_termination_and_json_round_trips(tmp_path):
    payload = '</script><script id="injected">alert(1)</script>'
    model = Model(
        objects={
            "PART-001": ModelObject(
                id="PART-001",
                type="Part",
                attributes={"Name": payload},
                source_file="mbse/parts.md",
            )
        }
    )
    output = tmp_path / "index.html"

    export_viewer(model, output, project_name=payload)

    html = output.read_text(encoding="utf-8")
    generated_model = json.loads((tmp_path / "model.json").read_text(encoding="utf-8"))
    assert payload not in html
    assert '<\\/script><script id=\\"injected\\">' in html
    assert "&lt;/script&gt;&lt;script id=&quot;injected&quot;&gt;" in html
    assert generated_model["objects"][0]["name"] == payload


def test_view_asset_cannot_escape_output_directory(tmp_path):
    with pytest.raises(ValueError, match="safe relative path"):
        export_viewer(
            Model(),
            tmp_path / "index.html",
            views=[],
            view_assets={"../outside.svg": "<svg/>",},
        )


def test_manifest_rejects_duplicate_and_empty_view_ids():
    valid_fields = {"title": "View", "group": "Test", "type": "overview"}

    with pytest.raises(ValueError, match="Duplicate view ID"):
        build_viewer_manifest(
            "test",
            [ViewDefinition(id="same", **valid_fields), ViewDefinition(id="same", **valid_fields)],
        )
    with pytest.raises(ValueError, match="must not be empty"):
        build_viewer_manifest("test", [ViewDefinition(id="  ", **valid_fields)])


def test_manifest_rejects_unsafe_source_missing_asset_source_and_invalid_default():
    with pytest.raises(ValueError, match="safe relative path"):
        build_viewer_manifest(
            "test",
            [ViewDefinition(id="unsafe", title="Unsafe", group="Test", type="svg", source="../x.svg")],
        )
    with pytest.raises(ValueError, match="requires a source"):
        build_viewer_manifest(
            "test",
            [ViewDefinition(id="missing", title="Missing", group="Test", type="svg")],
        )
    with pytest.raises(ValueError, match="Default view"):
        build_viewer_manifest("test", default_view="missing")
