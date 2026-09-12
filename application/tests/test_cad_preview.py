import base64
import builtins
import json
import struct
from pathlib import Path

import pytest

from mbse_lite.cad.preview import unit_scale_to_m, validate_cad_preview
from mbse_lite.cad.protocol import CAD_ARTIFACT_FILENAMES, CAD_REQUIRED_CHECKS, CadWorkerError
from mbse_lite.cli import build_parser
from mbse_lite.core import load_model
from mbse_lite.viewer import export_viewer


COMPONENT_IDS = (
    "PART-001",
    "PART-004",
    "PART-005",
    "PART-008",
    "PART-010",
    "PART-011",
    "PART-012",
)


def garden_shed_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "garden_tool_shed"


def _glb(ids=COMPONENT_IDS) -> bytes:
    nodes = [{"name": "conceptual-preview"}]
    nodes.extend(
        {"name": object_id, "extras": {"mbse_id": object_id}}
        for object_id in ids
    )
    document = json.dumps(
        {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes},
        separators=(",", ":"),
    ).encode("utf-8")
    document += b" " * (-len(document) % 4)
    return struct.pack("<4sIII4s", b"glTF", 2, 20 + len(document), len(document), b"JSON") + document


def _publish_preview(directory: Path, *, unit="mm", authority="visualization-only", scope="conceptual-preview") -> None:
    directory.mkdir()
    backend = {"name": "cadquery", "version": "2.8.0", "internal_length_unit": unit}
    manifest = {
        "schema_version": "0.6",
        "generated_metadata": True,
        "source_of_truth": "project Markdown",
        "backend": backend,
        "artifacts": [
            {"file": "footprint.step", "format": "STEP", "authority": "engineering", "scope": "footprint-only"},
            {"file": "conceptual-preview.step", "format": "STEP", "authority": "visualization-only", "scope": "conceptual-preview"},
            {"file": "conceptual-preview.glb", "format": "GLB", "authority": authority, "scope": scope},
        ],
        "engineering_inputs": {},
        "visualization_only_inputs": {},
        "stable_identity": {
            "in_memory_component_names": list(COMPONENT_IDS),
            "step": {
                "preserves_all_component_ids": True,
                "observed_component_ids": list(COMPONENT_IDS),
            },
            "glb": {
                "preserves_all_component_ids_as_node_names": True,
                "observed_component_ids": list(COMPONENT_IDS),
                "preserves_current_viewer_extras_mbse_id": True,
                "observed_extras_mbse_ids": list(COMPONENT_IDS),
            },
        },
    }
    (directory / "footprint.step").write_bytes(b"footprint")
    (directory / "conceptual-preview.step").write_bytes(b"conceptual step")
    (directory / "conceptual-preview.glb").write_bytes(_glb())
    (directory / "cad-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    artifacts = [
        {"file": filename, "size_bytes": (directory / filename).stat().st_size}
        for filename in CAD_ARTIFACT_FILENAMES
    ]
    completion = {
        "schema_version": 1,
        "job_id": "test-job",
        "status": "completed",
        "backend": backend,
        "artifacts": artifacts,
        "checks": {**{name: True for name in CAD_REQUIRED_CHECKS}, "verified_footprint_extent_mm": {"x": "4000", "y": "1200", "z": "0"}},
        "component_ids": list(COMPONENT_IDS),
        "step_component_ids": list(COMPONENT_IDS),
        "glb_node_names": ["conceptual-preview", *COMPONENT_IDS],
        "glb_component_ids": list(COMPONENT_IDS),
        "glb_mbse_ids": list(COMPONENT_IDS),
    }
    (directory / "cad-job-result.json").write_text(json.dumps(completion), encoding="utf-8")


def _rewrite_json(path: Path, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def _refresh_manifest_size(directory: Path) -> None:
    size = (directory / "cad-manifest.json").stat().st_size
    _rewrite_json(
        directory / "cad-job-result.json",
        lambda value: next(
            item for item in value["artifacts"] if item["file"] == "cad-manifest.json"
        ).update(size_bytes=size),
    )


def test_unit_scale_to_m_supports_only_current_architecture_units():
    assert unit_scale_to_m("mm") == 0.001
    assert unit_scale_to_m("m") == 1.0
    with pytest.raises(CadWorkerError, match="Unsupported CAD preview length unit"):
        unit_scale_to_m("cm")


def test_view_cli_accepts_only_an_explicit_cad_preview_directory():
    args = build_parser().parse_args(
        ["view", "project", "--cad-preview-dir", "cad", "--no-open"]
    )
    assert args.cad_preview_dir == Path("cad")
    assert args.no_open is True


def test_default_view_path_remains_custom_and_has_no_cad_notice(tmp_path):
    output = tmp_path / "default" / "index.html"
    export_viewer(load_model(garden_shed_project()), output, project_name="garden_tool_shed")

    manifest = json.loads((output.parent / "viewer.json").read_text(encoding="utf-8"))
    view = next(item for item in manifest["views"] if item["id"] == "conceptual-3d")
    html = output.read_text(encoding="utf-8")

    assert view["source"] == "views/model.glb"
    assert "viewer_scale" not in view["config"]
    assert "Conceptual CAD preview — visualization only" not in html
    assert (output.parent / "views" / "model.glb").is_file()


def test_valid_cad_preview_replaces_only_3d_asset_and_embeds_metadata(tmp_path):
    cad = tmp_path / "cad"
    _publish_preview(cad)
    output = tmp_path / "cad-view" / "index.html"

    export_viewer(
        load_model(garden_shed_project()),
        output,
        project_name="garden_tool_shed",
        cad_preview_dir=cad,
    )

    manifest = json.loads((output.parent / "viewer.json").read_text(encoding="utf-8"))
    view = next(item for item in manifest["views"] if item["id"] == "conceptual-3d")
    html = output.read_text(encoding="utf-8")
    glb = (cad / "conceptual-preview.glb").read_bytes()

    assert view["source"] == "views/conceptual-preview.glb"
    assert view["config"] == {
        "geometry_status": "conceptual",
        "asset_role": "conceptual-cad-preview",
        "authority": "visualization-only",
        "source_unit": "mm",
        "viewer_scale": 0.001,
        "identity_contract": "extras.mbse_id",
        "notice": "Conceptual CAD preview — visualization only",
    }
    assert (output.parent / "views" / "conceptual-preview.glb").read_bytes() == glb
    assert not (output.parent / "views" / "model.glb").exists()
    assert base64.b64encode(glb).decode("ascii") in html
    assert "fetch(" not in html and "cdn.jsdelivr.net" not in html
    assert "loader.parse(arrayBuffer" in html
    assert "if (notice) host.appendChild(notice)" in html


def test_cad_preview_path_does_not_import_cadquery_or_ocp(tmp_path, monkeypatch):
    cad = tmp_path / "cad"
    _publish_preview(cad)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.casefold() in {"cadquery", "ocp"}:
            raise AssertionError(f"optional CAD dependency imported: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    export_viewer(
        load_model(garden_shed_project()),
        tmp_path / "viewer" / "index.html",
        cad_preview_dir=cad,
    )


def test_missing_or_malformed_completion_is_rejected(tmp_path):
    cad = tmp_path / "cad"
    cad.mkdir()
    with pytest.raises(CadWorkerError, match="missing completion record"):
        validate_cad_preview(cad)
    (cad / "cad-job-result.json").write_text("{", encoding="utf-8")
    with pytest.raises(CadWorkerError, match="invalid completion record"):
        validate_cad_preview(cad)


def test_missing_preview_glb_is_rejected(tmp_path):
    cad = tmp_path / "cad"
    _publish_preview(cad)
    (cad / "conceptual-preview.glb").unlink()
    with pytest.raises(CadWorkerError, match="missing, empty, or changed"):
        validate_cad_preview(cad)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("authority", "engineering", "visualization-only authority"),
        ("scope", "full-cad", "conceptual-preview scope"),
    ],
)
def test_wrong_preview_authority_or_scope_is_rejected(tmp_path, field, value, message):
    cad = tmp_path / "cad"
    kwargs = {field: value}
    _publish_preview(cad, **kwargs)
    with pytest.raises(CadWorkerError, match=message):
        validate_cad_preview(cad)


def test_incomplete_actual_extras_identity_is_rejected(tmp_path):
    cad = tmp_path / "cad"
    _publish_preview(cad)
    glb_path = cad / "conceptual-preview.glb"
    glb_path.write_bytes(_glb(COMPONENT_IDS[:-1]))
    _rewrite_json(
        cad / "cad-job-result.json",
        lambda value: next(
            item for item in value["artifacts"] if item["file"] == "conceptual-preview.glb"
        ).update(size_bytes=glb_path.stat().st_size),
    )
    with pytest.raises(CadWorkerError, match="actual GLB"):
        validate_cad_preview(cad)


def test_unsupported_manifest_unit_is_rejected(tmp_path):
    cad = tmp_path / "cad"
    _publish_preview(cad, unit="cm")
    with pytest.raises(CadWorkerError, match="Unsupported CAD preview length unit"):
        validate_cad_preview(cad)


def test_renderer_scales_before_bounds_and_keeps_selection_contract(tmp_path):
    cad = tmp_path / "cad"
    _publish_preview(cad)
    output = tmp_path / "viewer" / "index.html"
    export_viewer(load_model(garden_shed_project()), output, cad_preview_dir=cad)
    html = output.read_text(encoding="utf-8")

    assert html.index("modelRoot.scale.setScalar(viewerScale)") < html.index(
        "new THREE.Box3().setFromObject(modelRoot)"
    )
    assert "current.userData?.mbse_id" in html
    assert "current.name" not in html
    assert "context.setSelectedObject(mbseId)" in html
    assert "applyHighlight(id)" in html
    assert "const clickMovementThreshold = 5" in html
    assert "const isClick = !pointerStart.moved && movement < clickMovementThreshold" in html
