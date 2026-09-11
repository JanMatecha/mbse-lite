import json
from pathlib import Path

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


def test_default_manifest_defines_grouped_navigation_and_asset_views():
    manifest = build_viewer_manifest("demo_project")

    assert manifest["schema_version"] == "0.1"
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

