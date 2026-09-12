import copy
import json
import shutil
import sys
import uuid
from pathlib import Path

import pytest

if sys.platform.startswith("win"):
    pytest.skip(
        "direct CadQuery tests run in Linux CI; Windows uses the isolated worker",
        allow_module_level=True,
    )

cq = pytest.importorskip("cadquery", reason="requires the optional cad dependency")

from mbse_lite.cad.cadquery_backend import (  # noqa: E402
    build_authoritative_footprint,
    build_conceptual_preview,
    execute_cad_job,
)
from mbse_lite.cad.protocol import (  # noqa: E402
    build_cad_job_request,
    parse_cad_job_request,
)
from mbse_lite.core import ModelObject, load_model  # noqa: E402
from mbse_lite.editing import UpdateObjectAttribute, update_object_attribute  # noqa: E402
from mbse_lite.visualization import (  # noqa: E402
    GARDEN_SHED_PROFILE,
    GARDEN_SHED_REQUIRED_ROLES,
    build_garden_shed_geometry_spec,
    build_garden_shed_visualization_spec,
    resolve_visualization_profile,
)


EXPECTED_COMPONENT_IDS = {
    "PART-001",
    "PART-004",
    "PART-005",
    "PART-008",
    "PART-010",
    "PART-011",
    "PART-012",
}


def garden_shed_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "garden_tool_shed"


def garden_shed_spec(project: Path | None = None):
    model = load_model(project or garden_shed_project())
    roles = resolve_visualization_profile(
        model, GARDEN_SHED_PROFILE, GARDEN_SHED_REQUIRED_ROLES
    )
    assert roles is not None
    return model, build_garden_shed_visualization_spec(roles)


def extent(shape):
    bounds = shape.BoundingBox()
    return (bounds.xlen, bounds.ylen, bounds.zlen)


def execute_for_model(model, output_dir):
    roles = resolve_visualization_profile(
        model, GARDEN_SHED_PROFILE, GARDEN_SHED_REQUIRED_ROLES
    )
    assert roles is not None
    spec = build_garden_shed_visualization_spec(roles)
    request = build_cad_job_request(spec, output_dir, str(uuid.uuid4()))
    return execute_cad_job(parse_cad_job_request(request))


def test_authoritative_footprint_is_a_zero_thickness_4000_by_1200_face(tmp_path):
    _, spec = garden_shed_spec()

    footprint = build_authoritative_footprint(spec.geometry)
    output = tmp_path / "footprint.step"
    footprint.shape.export(str(output), "STEP", unit="MM")
    imported = cq.importers.importStep(str(output), unit="MM").val()

    assert footprint.shape.ShapeType() == "Face"
    assert extent(footprint.shape) == pytest.approx((4000.0, 1200.0, 0.0))
    assert output.stat().st_size > 0
    assert extent(imported) == pytest.approx((4000.0, 1200.0, 0.0))


def test_structured_dimensions_but_not_requirement_prose_drive_cad(
    tmp_path,
):
    project = tmp_path / "garden_tool_shed"
    shutil.copytree(garden_shed_project(), project)
    _, original_spec = garden_shed_spec(project)
    original_extent = extent(build_authoritative_footprint(original_spec.geometry).shape)

    requirements = project / "mbse" / "02_requirements.md"
    prose = requirements.read_text(encoding="utf-8")
    requirements.write_text(
        prose.replace(
            "The design shall target the approximate external footprint defined by the structured target dimensions in this requirement.",
            "Changed free prose mentions 99 m by 88 m but is not a CAD parameter.",
        ),
        encoding="utf-8",
    )
    _, prose_spec = garden_shed_spec(project)
    prose_extent = extent(build_authoritative_footprint(prose_spec.geometry).shape)

    update_object_attribute(
        project,
        UpdateObjectAttribute(
            object_id="REQ-008",
            attribute="Target Length [m]",
            new_value="4.5",
            expected_old_value="4.0",
        ),
    )
    _, changed_spec = garden_shed_spec(project)
    changed_extent = extent(build_authoritative_footprint(changed_spec.geometry).shape)

    assert prose_extent == pytest.approx(original_extent)
    assert changed_extent == pytest.approx((4500.0, 1200.0, 0.0))


def test_conceptual_preview_uses_only_explicit_roles_for_stable_components():
    model, spec = garden_shed_spec()
    model.objects["CON-999"] = ModelObject(
        id="CON-999",
        type="Concept",
        attributes={"Name": "Unrelated", "Status": "Preferred candidate"},
    )
    roles = resolve_visualization_profile(
        model, GARDEN_SHED_PROFILE, GARDEN_SHED_REQUIRED_ROLES
    )
    assert roles is not None
    changed_spec = build_garden_shed_visualization_spec(roles)

    preview = build_conceptual_preview(changed_spec)

    assert set(preview.component_ids) == EXPECTED_COMPONENT_IDS
    assert "CON-999" not in preview.component_ids
    assert preview.authoritative_length_mm == spec.geometry.external_length.value * 1000
    assert preview.authoritative_depth_mm == spec.geometry.external_depth.value * 1000
    assert set(preview.assembly.objects) >= EXPECTED_COMPONENT_IDS
    assert extent(preview.assembly.objects["PART-001"].obj) == pytest.approx(
        (4000.0, 1200.0, 2200.0)
    )


def test_full_export_classifies_artifacts_and_records_identity_evidence(tmp_path):
    model = load_model(garden_shed_project())

    result = execute_for_model(model, tmp_path / "cad")
    manifest = json.loads(
        (tmp_path / "cad" / "cad-manifest.json").read_text(encoding="utf-8")
    )

    assert {path.name for path in result.artifacts} == {
        "footprint.step",
        "conceptual-preview.step",
        "conceptual-preview.glb",
        "cad-manifest.json",
    }
    assert all(path.stat().st_size > 0 for path in result.artifacts)
    assert manifest == result.manifest
    assert manifest["schema_version"] == "0.6"
    assert manifest["generated_metadata"] is True
    assert manifest["source_of_truth"] == "project Markdown"
    assert manifest["backend"] == {
        "name": "cadquery",
        "version": "2.8.0",
        "internal_length_unit": "mm",
    }
    artifacts = {item["file"]: item for item in manifest["artifacts"]}
    assert artifacts["footprint.step"] == {
        "file": "footprint.step",
        "format": "STEP",
        "authority": "engineering",
        "scope": "footprint-only",
        "source_object_ids": ["REQ-008"],
        "extent_mm": {"x": "4000", "y": "1200", "z": "0"},
    }
    assert {
        artifacts[name]["authority"]
        for name in ("conceptual-preview.step", "conceptual-preview.glb")
    } == {"visualization-only"}
    assert set(manifest["stable_identity"]["in_memory_component_names"]) == (
        EXPECTED_COMPONENT_IDS
    )
    assert set(result.glb_component_ids) == EXPECTED_COMPONENT_IDS
    assert set(result.step_component_ids) == EXPECTED_COMPONENT_IDS
    assert result.glb_mbse_ids == ()
    assert manifest["stable_identity"]["glb"][
        "preserves_all_component_ids_as_node_names"
    ] is True
    assert manifest["stable_identity"]["glb"][
        "preserves_current_viewer_extras_mbse_id"
    ] is False
    assert manifest["stable_identity"]["step"]["observed_component_ids"] == list(
        result.step_component_ids
    )


def test_cad_export_is_semantically_deterministic(tmp_path):
    model = load_model(garden_shed_project())

    first = execute_for_model(copy.deepcopy(model), tmp_path / "first")
    second = execute_for_model(copy.deepcopy(model), tmp_path / "second")

    assert first.manifest == second.manifest
    assert first.component_ids == second.component_ids
    assert first.glb_component_ids == second.glb_component_ids
