import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import mbse_lite.cad.cadquery_backend as cadquery_backend
import mbse_lite.cad.worker as cad_worker
from mbse_lite.cad.protocol import (
    CAD_ARTIFACT_FILENAMES,
    CAD_COMPONENT_ROLES,
    CAD_REQUIRED_CHECKS,
    CadExportError,
    build_cad_job_request,
)
from mbse_lite.core import load_model
from mbse_lite.visualization import (
    GARDEN_SHED_PROFILE,
    GARDEN_SHED_REQUIRED_ROLES,
    build_garden_shed_visualization_spec,
    resolve_visualization_profile,
)


def garden_shed_project() -> Path:
    return Path(__file__).resolve().parents[2] / "projects" / "garden_tool_shed"


def _request_path(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    model = load_model(garden_shed_project())
    roles = resolve_visualization_profile(
        model, GARDEN_SHED_PROFILE, GARDEN_SHED_REQUIRED_ROLES
    )
    assert roles is not None
    request = build_cad_job_request(
        build_garden_shed_visualization_spec(roles),
        tmp_path / "cad",
        "current-job-id",
    )
    output_dir = Path(request["output_dir"])
    output_dir.mkdir()
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    return path, request


def _valid_backend_result(request: dict[str, object], *, create_all=True):
    output_dir = Path(request["output_dir"])
    roles = request["visualization"]["roles"]
    component_ids = tuple(roles[role]["object_id"] for role in CAD_COMPONENT_ROLES)
    manifest = {
        "schema_version": "0.6",
        "generated_metadata": True,
        "source_of_truth": "project Markdown",
        "backend": {
            "name": "cadquery",
            "version": "2.8.0",
            "internal_length_unit": "mm",
        },
    }
    filenames = CAD_ARTIFACT_FILENAMES if create_all else CAD_ARTIFACT_FILENAMES[:-1]
    for filename in filenames:
        path = output_dir / filename
        if filename == "cad-manifest.json":
            path.write_text(json.dumps(manifest), encoding="utf-8")
        else:
            path.write_bytes(f"valid {filename}".encode())
    return SimpleNamespace(
        artifacts=tuple(output_dir / filename for filename in CAD_ARTIFACT_FILENAMES),
        manifest=manifest,
        checks={
            **{name: True for name in CAD_REQUIRED_CHECKS},
            "verified_footprint_extent_mm": request[
                "expected_footprint_extent_mm"
            ],
        },
        component_ids=component_ids,
        step_component_ids=component_ids,
        glb_node_names=("conceptual-preview", *component_ids),
        glb_component_ids=component_ids,
        glb_mbse_ids=component_ids,
    )


class _RecordedStream:
    def __init__(self, name: str, events: list[str]):
        self.name = name
        self.events = events

    def write(self, value: str) -> int:
        self.events.append(f"{self.name}-write")
        return len(value)

    def flush(self) -> None:
        self.events.append(f"{self.name}-flush")


def test_success_publishes_current_completion_then_flushes_and_exits(
    tmp_path, monkeypatch
):
    request_path, request = _request_path(tmp_path)
    result = _valid_backend_result(request)
    events: list[str] = []
    real_publish = cad_worker._write_completion_record

    monkeypatch.setattr(cadquery_backend, "execute_cad_job", lambda job: result)

    def publish(path, value):
        real_publish(path, value)
        published = json.loads(path.read_text(encoding="utf-8"))
        assert published["job_id"] == request["job_id"]
        assert published["status"] == "completed"
        events.append("completion-published")

    def controlled_exit(code):
        completion = Path(request["output_dir"]) / "cad-job-result.json"
        assert json.loads(completion.read_text(encoding="utf-8"))["job_id"] == (
            request["job_id"]
        )
        events.append(f"exit-{code}")

    monkeypatch.setattr(cad_worker, "_write_completion_record", publish)
    monkeypatch.setattr(cad_worker.sys, "stdout", _RecordedStream("stdout", events))
    monkeypatch.setattr(cad_worker.sys, "stderr", _RecordedStream("stderr", events))
    monkeypatch.setattr(cad_worker.os, "_exit", controlled_exit)

    assert cad_worker.main([str(request_path)]) == 0
    assert events == [
        "completion-published",
        "stdout-flush",
        "stderr-flush",
        "exit-0",
    ]


def test_failure_before_completion_never_uses_controlled_success_exit(
    tmp_path, monkeypatch, capsys
):
    request_path, request = _request_path(tmp_path)

    def fail(job):
        raise CadExportError("semantic validation failed")

    monkeypatch.setattr(cadquery_backend, "execute_cad_job", fail)
    monkeypatch.setattr(
        cad_worker.os,
        "_exit",
        lambda code: pytest.fail("failure path must not invoke os._exit"),
    )

    assert cad_worker.main([str(request_path)]) == 1
    assert "semantic validation failed" in capsys.readouterr().err
    assert not (Path(request["output_dir"]) / "cad-job-result.json").exists()


def test_missing_backend_artifact_never_publishes_or_exits_successfully(
    tmp_path, monkeypatch
):
    request_path, request = _request_path(tmp_path)
    result = _valid_backend_result(request, create_all=False)
    published = False

    monkeypatch.setattr(cadquery_backend, "execute_cad_job", lambda job: result)

    def must_not_publish(path, value):
        nonlocal published
        published = True

    monkeypatch.setattr(cad_worker, "_write_completion_record", must_not_publish)
    monkeypatch.setattr(
        cad_worker.os,
        "_exit",
        lambda code: pytest.fail("invalid artifacts must not invoke os._exit"),
    )

    assert cad_worker.main([str(request_path)]) == 1
    assert published is False
    assert not (Path(request["output_dir"]) / "cad-job-result.json").exists()


def test_failed_semantic_check_never_publishes_or_exits_successfully(
    tmp_path, monkeypatch
):
    request_path, request = _request_path(tmp_path)
    result = _valid_backend_result(request)
    result.checks["manifest_complete"] = False

    monkeypatch.setattr(cadquery_backend, "execute_cad_job", lambda job: result)
    monkeypatch.setattr(
        cad_worker.os,
        "_exit",
        lambda code: pytest.fail("failed checks must not invoke os._exit"),
    )

    assert cad_worker.main([str(request_path)]) == 1
    assert not (Path(request["output_dir"]) / "cad-job-result.json").exists()


def test_incomplete_glb_extras_evidence_never_publishes_success(
    tmp_path, monkeypatch
):
    request_path, request = _request_path(tmp_path)
    result = _valid_backend_result(request)
    result.glb_mbse_ids = result.glb_mbse_ids[:-1]

    monkeypatch.setattr(cadquery_backend, "execute_cad_job", lambda job: result)
    monkeypatch.setattr(
        cad_worker.os,
        "_exit",
        lambda code: pytest.fail("invalid identity must not invoke os._exit"),
    )

    assert cad_worker.main([str(request_path)]) == 1
    assert not (Path(request["output_dir"]) / "cad-job-result.json").exists()
