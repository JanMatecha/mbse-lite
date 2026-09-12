import base64
import copy
import json
import struct
from pathlib import Path
from xml.etree import ElementTree

import pytest

from mbse_lite.core import Model, ModelObject, load_model
from mbse_lite.browser_assets import MERMAID_VERSION, THREE_VERSION
from mbse_lite.view_architecture import (
    MBSE_AREA,
    PROJECT_MANAGEMENT_AREA,
    SUPPORTED_VIEW_TYPES,
    ViewDefinition,
    build_viewer_manifest,
)
from mbse_lite.viewer import export_viewer
from mbse_lite.visualization import (
    build_generated_views,
    load_visualization_profiles,
    validate_visualizations,
)
from mbse_lite.visualization.garden_shed import GARDEN_SHED_REQUIRED_ROLES


def demo_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "demo_project"


def garden_shed_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "garden_tool_shed"


def glb_json(glb: bytes) -> dict[str, object]:
    magic, version, total_length = struct.unpack_from("<4sII", glb)
    json_length, json_type = struct.unpack_from("<I4s", glb, 12)
    assert magic == b"glTF"
    assert version == 2
    assert total_length == len(glb)
    assert json_type == b"JSON"
    return json.loads(glb[20 : 20 + json_length].decode("utf-8").rstrip(" "))


def test_default_manifest_defines_grouped_navigation_and_asset_views():
    manifest = build_viewer_manifest("demo_project")

    assert manifest["schema_version"] == "0.4"
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


def test_viewer_bundle_contains_pinned_offline_browser_dependencies(tmp_path):
    output = tmp_path / "index.html"

    export_viewer(load_model(demo_project()), output, project_name="Demo Project")

    html = output.read_text(encoding="utf-8")
    vendor = tmp_path / "assets" / "vendor"
    dependency_manifest = json.loads(
        (vendor / "manifest.json").read_text(encoding="utf-8")
    )

    assert "cdn.jsdelivr.net" not in html
    assert "import('three')" not in html
    assert f'src="assets/vendor/three-viewer-{THREE_VERSION}.min.js"' in html
    assert f'src="assets/vendor/mermaid-{MERMAID_VERSION}.min.js"' in html
    assert (vendor / f"three-viewer-{THREE_VERSION}.min.js").stat().st_size > 500_000
    assert (vendor / f"mermaid-{MERMAID_VERSION}.min.js").stat().st_size > 1_000_000
    assert (vendor / "three-LICENSE.txt").exists()
    assert (vendor / "mermaid-LICENSE.txt").exists()
    assert dependency_manifest["dependencies"]["three"]["version"] == THREE_VERSION
    assert dependency_manifest["dependencies"]["mermaid"]["version"] == MERMAID_VERSION
    assert dependency_manifest["build_tool"] == "esbuild@0.25.9"


def test_garden_shed_visualization_profile_resolves_required_roles_by_id():
    model = load_model(garden_shed_project())

    profile = load_visualization_profiles(model)["garden_shed"]

    assert set(profile.roles) == set(GARDEN_SHED_REQUIRED_ROLES)
    assert {mapping.object_id for mapping in profile.roles.values()} == {
        "PART-001",
        "PART-004",
        "PART-005",
        "PART-008",
        "PART-010",
        "PART-011",
        "PART-012",
    }
    assert all(mapping.expected_type == "Part" for mapping in profile.roles.values())
    assert validate_visualizations(model) == []


def test_garden_shed_generation_does_not_depend_on_mapped_object_names():
    model = load_model(garden_shed_project())
    profile = load_visualization_profiles(model)["garden_shed"]
    for index, mapping in enumerate(profile.roles.values(), start=1):
        model.objects[mapping.object_id].attributes["Name"] = f"Renamed part {index}"

    generated = build_generated_views(model)

    assert {view.id for view in generated.views} >= {"floor-plan", "conceptual-3d"}
    assert generated.assets["views/model.glb"].startswith(b"glTF")


def test_missing_garden_shed_profile_role_fails_clearly():
    model = copy.deepcopy(load_model(garden_shed_project()))
    for table_key, rows in model.tables.items():
        if rows and "Visualization Profile" in rows[0]:
            model.tables[table_key] = [row for row in rows if row["Role"] != "shelving"]
            break

    with pytest.raises(ValueError, match="missing required roles: shelving"):
        build_generated_views(model)
    assert validate_visualizations(model) == [
        ("ERROR", "Visualization profile 'garden_shed' is missing required roles: shelving")
    ]


def test_missing_profile_object_id_and_wrong_type_fail_clearly():
    missing_model = copy.deepcopy(load_model(garden_shed_project()))
    wrong_type_model = copy.deepcopy(load_model(garden_shed_project()))
    for model, object_id, expected_type in (
        (missing_model, "PART-999", "Part"),
        (wrong_type_model, "PART-001", "Requirement"),
    ):
        for rows in model.tables.values():
            if rows and "Visualization Profile" in rows[0]:
                rows[0]["Object ID"] = object_id
                rows[0]["Expected Type"] = expected_type
                break

    with pytest.raises(ValueError, match="missing object ID 'PART-999'"):
        build_generated_views(missing_model)
    with pytest.raises(ValueError, match="of type 'Part'; expected 'Requirement'"):
        build_generated_views(wrong_type_model)
    assert validate_visualizations(missing_model)[0][0] == "ERROR"
    assert validate_visualizations(wrong_type_model)[0][0] == "ERROR"


def test_demo_project_does_not_activate_garden_shed_visualization():
    model = load_model(demo_project())

    assert load_visualization_profiles(model) == {}
    assert build_generated_views(model).views == ()
    assert build_generated_views(model).assets == {}


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


def test_garden_shed_registry_emits_binary_glb_with_stable_model_ids():
    model = load_model(garden_shed_project())

    generated = build_generated_views(model)

    glb = generated.assets["views/model.glb"]
    assert isinstance(glb, bytes)
    assert build_generated_views(model).assets["views/model.glb"] == glb
    document = glb_json(glb)
    mapped_ids = {
        node.get("extras", {}).get("mbse_id")
        for node in document["nodes"]
        if node.get("extras", {}).get("mbse_id")
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


def test_garden_shed_bundle_contains_conceptual_3d_manifest_and_embedded_glb(tmp_path):
    output = tmp_path / "index.html"
    export_viewer(load_model(garden_shed_project()), output, project_name="garden_tool_shed")

    manifest = json.loads((tmp_path / "viewer.json").read_text(encoding="utf-8"))
    model_view = next(view for view in manifest["views"] if view["id"] == "conceptual-3d")
    glb = (tmp_path / "views" / "model.glb").read_bytes()
    html = output.read_text(encoding="utf-8")

    assert model_view["title"] == "3D"
    assert model_view["group"] == "Geometry"
    assert model_view["type"] == "gltf"
    assert model_view["source"] == "views/model.glb"
    assert model_view["config"]["geometry_status"] == "conceptual"
    assert glb.startswith(b"glTF")
    assert base64.b64encode(glb).decode("ascii") in html
    assert "const embeddedBinaryViewAssets" in html
    assert "base64ToArrayBuffer" in html
    assert "fetch(view.source" not in html


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


def test_gltf_renderer_uses_three_raycasting_shared_selection_and_cleanup(tmp_path):
    output = tmp_path / "index.html"
    export_viewer(load_model(garden_shed_project()), output, project_name="garden_tool_shed")

    html = output.read_text(encoding="utf-8")

    assert f"three-viewer-{THREE_VERSION}.min.js" in html
    assert "new GLTFLoader()" in html
    assert ".parse(arrayBuffer" in html
    assert "new THREE.Raycaster()" in html
    assert "context.setSelectedObject(mbseId)" in html
    assert "function restoreHighlights()" in html
    assert "onSelectionChanged(id)" in html
    assert "disposeObjectResources(parsedScenes)" in html
    assert "removeEventListener('pointerdown', pointerDownHandler)" in html
    assert "removeEventListener('pointermove', pointerMoveHandler)" in html
    assert "removeEventListener('pointerup', pointerUpHandler)" in html
    assert "removeEventListener('pointercancel', pointerCancelHandler)" in html
    assert "cancelAnimationFrame(animationFrame)" in html
    assert "resizeObserver?.disconnect()" in html
    assert "controls?.dispose()" in html
    assert "renderer?.dispose()" in html
    assert "renderer?.forceContextLoss?.()" in html
    assert "The local Three.js dependency is unavailable" in html


def test_gltf_renderer_selects_on_short_pointerup_but_not_orbit_drag(tmp_path):
    output = tmp_path / "index.html"
    export_viewer(load_model(garden_shed_project()), output, project_name="garden_tool_shed")

    html = output.read_text(encoding="utf-8")

    assert "const clickMovementThreshold = 5" in html
    assert "pointerDownHandler = event =>" in html
    assert "pointerMoveHandler = event =>" in html
    assert "pointerUpHandler = event =>" in html
    assert "Math.hypot(" in html
    assert "const isClick = !pointerStart.moved && movement < clickMovementThreshold" in html
    assert "if (isClick) selectAtPointer(event)" in html
    assert "addEventListener('pointerdown', pointerDownHandler)" in html
    assert "addEventListener('pointerup', pointerUpHandler)" in html


def test_dependency_and_malformed_asset_failures_are_local_to_their_views(tmp_path):
    output = tmp_path / "index.html"
    export_viewer(load_model(garden_shed_project()), output, project_name="garden_tool_shed")

    html = output.read_text(encoding="utf-8")

    assert "The local Mermaid dependency is unavailable" in html
    assert "The Mermaid diagram could not be rendered" in html
    assert "SVG source is invalid or unsafe" in html
    assert "The conceptual 3D model could not be rendered" in html
    assert "rendererFactories[view.type] || unsupportedRenderer" in html


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


def test_malformed_svg_is_quarantined_to_its_view(tmp_path):
    view = ViewDefinition(
        id="broken-svg",
        title="Broken SVG",
        group="Test",
        type="svg",
        source="views/broken.svg",
    )
    output = tmp_path / "index.html"

    export_viewer(
        Model(),
        output,
        project_name="Malformed asset",
        views=[view],
        view_assets={"views/broken.svg": "<svg><not-closed>"},
    )

    html = output.read_text(encoding="utf-8")
    assert not (tmp_path / "views" / "broken.svg").exists()
    assert "SVG asset is invalid or unsafe" in html
    assert "const viewAssetErrors" in html
    assert "assetErrors: viewAssetErrors" in html
    assert "rendererFactories[view.type] || unsupportedRenderer" in html


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


def test_binary_view_asset_cannot_escape_output_directory(tmp_path):
    with pytest.raises(ValueError, match="safe relative path"):
        export_viewer(
            Model(),
            tmp_path / "index.html",
            views=[],
            view_assets={"../outside.glb": b"glTF"},
        )


def test_unreferenced_binary_asset_is_written_but_not_embedded(tmp_path):
    payload = b"\x00binary-attachment\xff"
    output = tmp_path / "index.html"

    export_viewer(
        Model(),
        output,
        views=[],
        view_assets={"views/attachment.bin": payload},
    )

    assert (tmp_path / "views" / "attachment.bin").read_bytes() == payload
    assert base64.b64encode(payload).decode("ascii") not in output.read_text(encoding="utf-8")


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
