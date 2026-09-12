import json
import struct
import subprocess
from pathlib import Path

import pytest

from mbse_lite.cad import CadWorkerError, export_project_cad
from mbse_lite.cad.protocol import (
    CAD_ARTIFACT_FILENAMES,
    CAD_COMPONENT_ROLES,
    WINDOWS_HEAP_CORRUPTION_NTSTATUS,
    WINDOWS_HEAP_CORRUPTION_SIGNED,
)
import mbse_lite.cad.runner as cad_runner
from mbse_lite.core import load_model


def garden_shed_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "garden_tool_shed"


def _conceptual_glb(component_ids, *, omitted_extra=None):
    nodes = [{"name": "conceptual-preview"}]
    nodes.extend(
        {
            "name": object_id,
            "extras": (
                {} if object_id == omitted_extra else {"mbse_id": object_id}
            ),
        }
        for object_id in component_ids
    )
    document = json.dumps(
        {"asset": {"version": "2.0"}, "nodes": nodes}, separators=(",", ":")
    ).encode("utf-8")
    document += b" " * (-len(document) % 4)
    length = 20 + len(document)
    return struct.pack("<4sIII4s", b"glTF", 2, length, len(document), b"JSON") + document


def _valid_manifest(request, backend, component_ids, glb_mbse_ids=()):
    geometry = request["geometry"]
    defaults = request["visualization"]["defaults"]
    conceptual_sources = [
        geometry["source_object_id"],
        *component_ids,
        *request["visualization"]["displayed_candidate_ids"],
    ]
    return {
        "schema_version": "0.6",
        "generated_metadata": True,
        "source_of_truth": "project Markdown",
        "backend": backend,
        "artifacts": [
            {
                "file": "footprint.step",
                "format": "STEP",
                "authority": "engineering",
                "scope": "footprint-only",
                "source_object_ids": [geometry["source_object_id"]],
                "extent_mm": request["expected_footprint_extent_mm"],
            },
            {
                "file": "conceptual-preview.step",
                "format": "STEP",
                "authority": "visualization-only",
                "scope": "conceptual-preview",
                "source_object_ids": conceptual_sources,
            },
            {
                "file": "conceptual-preview.glb",
                "format": "GLB",
                "authority": "visualization-only",
                "scope": "conceptual-preview",
                "source_object_ids": conceptual_sources,
            },
        ],
        "engineering_inputs": {
            "source_object_id": geometry["source_object_id"],
            "external_length": geometry["external_length"],
            "external_depth": geometry["external_depth"],
        },
        "visualization_only_inputs": {
            "conceptual_height_m": defaults["conceptual_height"],
            "wall_thickness_m": defaults["wall_thickness"],
            "floor_thickness_m": defaults["floor_thickness"],
            "door_height_m": defaults["door_height"],
            "shelving_height_m": defaults["shelving_height"],
            "ramp_length_m": defaults["ramp_length"],
            "mower_fraction": defaults["mower_fraction"],
            "shelving_fraction": defaults["shelving_fraction"],
            "main_door_start": defaults["main_door_start"],
            "main_door_fraction": defaults["main_door_fraction"],
            "mower_door_start": defaults["mower_door_start"],
            "mower_door_fraction": defaults["mower_door_fraction"],
        },
        "stable_identity": {
            "in_memory_component_names": component_ids,
            "step": {
                "preserves_all_component_ids": True,
                "observed_component_ids": component_ids,
            },
            "glb": {
                "preserves_all_component_ids_as_node_names": True,
                "observed_component_ids": component_ids,
                "preserves_current_viewer_extras_mbse_id": bool(glb_mbse_ids),
                "observed_extras_mbse_ids": list(glb_mbse_ids),
            },
        },
    }


def _publish_valid_result(
    command,
    returncode=0,
    *,
    missing_artifact=None,
    completion_job_id=None,
):
    request = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
    output_dir = Path(request["output_dir"])
    roles = request["visualization"]["roles"]
    component_ids = [roles[role]["object_id"] for role in CAD_COMPONENT_ROLES]
    backend = {
        "name": "cadquery",
        "version": "2.8.0",
        "internal_length_unit": "mm",
    }
    manifest = _valid_manifest(request, backend, component_ids, component_ids)
    (output_dir / "footprint.step").write_bytes(b"mock footprint STEP")
    (output_dir / "conceptual-preview.step").write_bytes(b"mock conceptual STEP")
    (output_dir / "conceptual-preview.glb").write_bytes(
        _conceptual_glb(component_ids)
    )
    (output_dir / "cad-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    artifact_evidence = [
        {
            "file": filename,
            "size_bytes": (output_dir / filename).stat().st_size,
        }
        for filename in CAD_ARTIFACT_FILENAMES
    ]
    completion = {
        "schema_version": 1,
        "job_id": completion_job_id or request["job_id"],
        "status": "completed",
        "backend": backend,
        "artifacts": artifact_evidence,
        "checks": {
            "authoritative_footprint_step_readable": True,
            "authoritative_footprint_extent_matches_request": True,
            "authoritative_footprint_zero_z_extent": True,
            "manifest_complete": True,
            "conceptual_artifacts_complete": True,
            "component_identity_checks_complete": True,
            "required_artifacts_nonempty": True,
            "verified_footprint_extent_mm": request[
                "expected_footprint_extent_mm"
            ],
        },
        "component_ids": component_ids,
        "step_component_ids": component_ids,
        "glb_node_names": ["conceptual-preview", *component_ids],
        "glb_component_ids": component_ids,
        "glb_mbse_ids": component_ids,
    }
    (output_dir / "cad-job-result.json").write_text(
        json.dumps(completion), encoding="utf-8"
    )
    if missing_artifact is not None:
        (output_dir / missing_artifact).unlink()
    return subprocess.CompletedProcess(command, returncode, stdout="", stderr="")


def _mock_worker(
    monkeypatch,
    returncode=0,
    *,
    publish=True,
    missing_artifact=None,
    completion_job_id=None,
):
    def run(command, **kwargs):
        assert command[1:3] == ["-m", "mbse_lite.cad.worker"]
        assert kwargs == {"check": False, "capture_output": True, "text": True}
        if publish:
            return _publish_valid_result(
                command,
                returncode,
                missing_artifact=missing_artifact,
                completion_job_id=completion_job_id,
            )
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr="")

    monkeypatch.setattr(cad_runner.subprocess, "run", run)


def test_zero_exit_with_valid_completion_is_success(tmp_path, monkeypatch):
    _mock_worker(monkeypatch)

    result = export_project_cad(load_model(garden_shed_project()), tmp_path / "cad")

    assert result.worker_exit_code == 0
    assert result.warning is None
    assert result.completion_record.is_file()


@pytest.mark.parametrize(
    "returncode", [WINDOWS_HEAP_CORRUPTION_NTSTATUS, WINDOWS_HEAP_CORRUPTION_SIGNED]
)
def test_exact_windows_heap_corruption_after_valid_completion_is_warning_success(
    tmp_path, monkeypatch, returncode
):
    _mock_worker(monkeypatch, returncode)

    result = export_project_cad(
        load_model(garden_shed_project()), tmp_path / "cad", _platform="win32"
    )

    assert result.worker_exit_code == returncode
    assert "0xC0000374" in result.warning
    assert "completed and validated" in result.warning


def test_windows_heap_corruption_without_completion_is_failure(tmp_path, monkeypatch):
    _mock_worker(monkeypatch, WINDOWS_HEAP_CORRUPTION_SIGNED, publish=False)

    with pytest.raises(CadWorkerError, match="did not publish completion record"):
        export_project_cad(
            load_model(garden_shed_project()), tmp_path / "cad", _platform="win32"
        )


def test_windows_heap_corruption_with_missing_artifact_is_failure(
    tmp_path, monkeypatch
):
    _mock_worker(
        monkeypatch,
        WINDOWS_HEAP_CORRUPTION_SIGNED,
        missing_artifact="conceptual-preview.glb",
    )

    with pytest.raises(CadWorkerError, match="missing, empty, or changed"):
        export_project_cad(
            load_model(garden_shed_project()), tmp_path / "cad", _platform="win32"
        )


def test_arbitrary_nonzero_exit_is_failure_even_with_valid_completion(
    tmp_path, monkeypatch
):
    _mock_worker(monkeypatch, 17)

    with pytest.raises(CadWorkerError, match="exited with code 17"):
        export_project_cad(
            load_model(garden_shed_project()), tmp_path / "cad", _platform="win32"
        )


def test_windows_access_violation_is_failure_even_with_valid_completion(
    tmp_path, monkeypatch
):
    _mock_worker(monkeypatch, 0xC0000005)

    with pytest.raises(CadWorkerError, match="exited with code 3221225477"):
        export_project_cad(
            load_model(garden_shed_project()), tmp_path / "cad", _platform="win32"
        )


def test_zero_exit_without_valid_completion_is_failure(tmp_path, monkeypatch):
    _mock_worker(monkeypatch, 0, publish=False)

    with pytest.raises(CadWorkerError, match="did not publish completion record"):
        export_project_cad(load_model(garden_shed_project()), tmp_path / "cad")


def test_zero_exit_with_malformed_completion_is_failure(tmp_path, monkeypatch):
    def run(command, **kwargs):
        completed = _publish_valid_result(command)
        output_dir = Path(
            json.loads(Path(command[-1]).read_text(encoding="utf-8"))["output_dir"]
        )
        (output_dir / "cad-job-result.json").write_text("{", encoding="utf-8")
        return completed

    monkeypatch.setattr(cad_runner.subprocess, "run", run)

    with pytest.raises(CadWorkerError, match="invalid completion record"):
        export_project_cad(load_model(garden_shed_project()), tmp_path / "cad")


def test_zero_exit_with_mismatched_job_id_is_failure(tmp_path, monkeypatch):
    _mock_worker(monkeypatch, completion_job_id="stale-job-id")

    with pytest.raises(CadWorkerError, match="wrong job ID"):
        export_project_cad(load_model(garden_shed_project()), tmp_path / "cad")


def test_known_windows_code_is_not_accepted_on_linux(tmp_path, monkeypatch):
    _mock_worker(monkeypatch, WINDOWS_HEAP_CORRUPTION_SIGNED)

    with pytest.raises(CadWorkerError, match="exited with code -1073740940"):
        export_project_cad(
            load_model(garden_shed_project()), tmp_path / "cad", _platform="linux"
        )


def test_stale_completion_record_cannot_satisfy_a_new_job(tmp_path, monkeypatch):
    output_dir = tmp_path / "cad"
    output_dir.mkdir()
    (output_dir / "cad-job-result.json").write_text(
        json.dumps({"job_id": "stale", "status": "completed"}), encoding="utf-8"
    )
    _mock_worker(monkeypatch, 0, publish=False)

    with pytest.raises(CadWorkerError, match="did not publish completion record"):
        export_project_cad(load_model(garden_shed_project()), output_dir)

    assert not (output_dir / "cad-job-result.json").exists()


def test_parent_rejects_glb_tampering_even_when_manifest_claims_success(
    tmp_path, monkeypatch
):
    def run(command, **kwargs):
        completed = _publish_valid_result(command)
        request = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        output_dir = Path(request["output_dir"])
        component_ids = [
            request["visualization"]["roles"][role]["object_id"]
            for role in CAD_COMPONENT_ROLES
        ]
        glb_path = output_dir / "conceptual-preview.glb"
        glb_path.write_bytes(
            _conceptual_glb(component_ids, omitted_extra=component_ids[0])
        )
        completion_path = output_dir / "cad-job-result.json"
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
        for artifact in completion["artifacts"]:
            if artifact["file"] == "conceptual-preview.glb":
                artifact["size_bytes"] = glb_path.stat().st_size
        completion_path.write_text(json.dumps(completion), encoding="utf-8")
        return completed

    monkeypatch.setattr(cad_runner.subprocess, "run", run)

    with pytest.raises(CadWorkerError, match="actual GLB"):
        export_project_cad(load_model(garden_shed_project()), tmp_path / "cad")
