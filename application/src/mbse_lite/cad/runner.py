from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Mapping

from ..core import Model, validate_model
from ..visualization import (
    GARDEN_SHED_PROFILE,
    GARDEN_SHED_REQUIRED_ROLES,
    build_garden_shed_visualization_spec,
    resolve_visualization_profile,
    validate_visualizations,
)
from .glb_identity import inspect_glb_identity
from .protocol import (
    CAD_ARTIFACT_FILENAMES,
    CAD_COMPONENT_ROLES,
    CAD_JOB_RESULT_FILENAME,
    CAD_JOB_SCHEMA_VERSION,
    CAD_REQUIRED_CHECKS,
    CadExportError,
    CadExportResult,
    CadWorkerError,
    build_cad_job_request,
    is_windows_heap_corruption_exit_code,
)


_COMPLETION_KEYS = {
    "schema_version",
    "job_id",
    "status",
    "backend",
    "artifacts",
    "checks",
    "component_ids",
    "step_component_ids",
    "glb_node_names",
    "glb_component_ids",
    "glb_mbse_ids",
}
_KNOWN_WINDOWS_WARNING = (
    "WARNING: the isolated CadQuery worker terminated during Windows interpreter "
    "shutdown with known upstream error 0xC0000374. Artifacts were completed and "
    "validated before shutdown."
)


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CadWorkerError(f"CAD worker {label} must be a JSON object")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CadWorkerError(f"CAD worker {label} must be a list of strings")
    return tuple(value)


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CadWorkerError(f"CAD worker did not publish {label}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CadWorkerError(
            f"CAD worker published an invalid {label}: {error}"
        ) from error
    return _mapping(value, label)


def _validate_backend(value: object) -> Mapping[str, Any]:
    backend = _mapping(value, "backend metadata")
    if set(backend) != {"name", "version", "internal_length_unit"}:
        raise CadWorkerError("CAD worker backend metadata has unexpected fields")
    if (
        backend.get("name") != "cadquery"
        or backend.get("internal_length_unit") != "mm"
    ):
        raise CadWorkerError(
            "CAD worker did not report the required CadQuery/mm backend"
        )
    if not isinstance(backend.get("version"), str) or not backend["version"]:
        raise CadWorkerError("CAD worker did not report a backend version")
    return backend


def _validate_manifest(
    manifest: Mapping[str, Any],
    request: Mapping[str, Any],
    backend: Mapping[str, Any],
    component_ids: tuple[str, ...],
    step_ids: tuple[str, ...],
    glb_ids: tuple[str, ...],
    glb_mbse_ids: tuple[str, ...],
) -> None:
    if set(manifest) != {
        "schema_version",
        "generated_metadata",
        "source_of_truth",
        "backend",
        "artifacts",
        "engineering_inputs",
        "visualization_only_inputs",
        "stable_identity",
    }:
        raise CadWorkerError("CAD manifest has unexpected or missing fields")
    if manifest.get("schema_version") != "0.6":
        raise CadWorkerError("CAD manifest has the wrong schema version")
    if manifest.get("generated_metadata") is not True:
        raise CadWorkerError("CAD manifest is not marked as generated metadata")
    if manifest.get("source_of_truth") != "project Markdown":
        raise CadWorkerError("CAD manifest changed the source-of-truth declaration")
    if manifest.get("backend") != backend:
        raise CadWorkerError("CAD completion and manifest backend metadata differ")

    request_geometry = _mapping(request.get("geometry"), "request geometry")
    expected_engineering = {
        "source_object_id": request_geometry.get("source_object_id"),
        "external_length": request_geometry.get("external_length"),
        "external_depth": request_geometry.get("external_depth"),
    }
    if manifest.get("engineering_inputs") != expected_engineering:
        raise CadWorkerError("CAD manifest engineering inputs differ from the request")

    artifact_values = manifest.get("artifacts")
    if not isinstance(artifact_values, list) or len(artifact_values) != 3:
        raise CadWorkerError("CAD manifest must classify exactly three CAD artifacts")
    if not all(isinstance(item, dict) for item in artifact_values):
        raise CadWorkerError("CAD manifest artifact classifications are malformed")
    artifacts = {item.get("file"): item for item in artifact_values}
    if set(artifacts) != {
        "footprint.step",
        "conceptual-preview.step",
        "conceptual-preview.glb",
    }:
        raise CadWorkerError("CAD manifest artifact classifications are incomplete")

    expected_extent = request.get("expected_footprint_extent_mm")
    footprint = artifacts["footprint.step"]
    if footprint != {
        "file": "footprint.step",
        "format": "STEP",
        "authority": "engineering",
        "scope": "footprint-only",
        "source_object_ids": [request_geometry.get("source_object_id")],
        "extent_mm": expected_extent,
    }:
        raise CadWorkerError(
            "CAD manifest authoritative footprint classification is invalid"
        )

    visualization = _mapping(request.get("visualization"), "request visualization")
    defaults = _mapping(
        visualization.get("defaults"), "request visualization defaults"
    )
    expected_visualization_inputs = {
        "conceptual_height_m": defaults.get("conceptual_height"),
        "wall_thickness_m": defaults.get("wall_thickness"),
        "floor_thickness_m": defaults.get("floor_thickness"),
        "door_height_m": defaults.get("door_height"),
        "shelving_height_m": defaults.get("shelving_height"),
        "ramp_length_m": defaults.get("ramp_length"),
        "mower_fraction": defaults.get("mower_fraction"),
        "shelving_fraction": defaults.get("shelving_fraction"),
        "main_door_start": defaults.get("main_door_start"),
        "main_door_fraction": defaults.get("main_door_fraction"),
        "mower_door_start": defaults.get("mower_door_start"),
        "mower_door_fraction": defaults.get("mower_door_fraction"),
    }
    if manifest.get("visualization_only_inputs") != expected_visualization_inputs:
        raise CadWorkerError(
            "CAD manifest visualization-only inputs differ from the request"
        )
    conceptual_sources = [
        request_geometry.get("source_object_id"),
        *component_ids,
        *visualization.get("displayed_candidate_ids", []),
    ]
    for filename, file_format in (
        ("conceptual-preview.step", "STEP"),
        ("conceptual-preview.glb", "GLB"),
    ):
        if artifacts[filename] != {
            "file": filename,
            "format": file_format,
            "authority": "visualization-only",
            "scope": "conceptual-preview",
            "source_object_ids": conceptual_sources,
        }:
            raise CadWorkerError(
                f"CAD manifest classification for {filename} is invalid"
            )

    stable = _mapping(manifest.get("stable_identity"), "manifest identity evidence")
    if set(stable) != {"in_memory_component_names", "step", "glb"}:
        raise CadWorkerError("CAD manifest identity evidence has unexpected fields")
    if stable.get("in_memory_component_names") != list(component_ids):
        raise CadWorkerError("CAD manifest in-memory component IDs are invalid")
    step = _mapping(stable.get("step"), "manifest STEP identity evidence")
    if set(step) != {"preserves_all_component_ids", "observed_component_ids"}:
        raise CadWorkerError(
            "CAD manifest STEP identity evidence has unexpected fields"
        )
    if step.get("preserves_all_component_ids") is not True:
        raise CadWorkerError("CAD manifest reports incomplete STEP component identity")
    if step.get("observed_component_ids") != list(step_ids):
        raise CadWorkerError(
            "CAD manifest STEP identity evidence differs from completion"
        )
    glb = _mapping(stable.get("glb"), "manifest GLB identity evidence")
    if set(glb) != {
        "preserves_all_component_ids_as_node_names",
        "observed_component_ids",
        "preserves_current_viewer_extras_mbse_id",
        "observed_extras_mbse_ids",
    }:
        raise CadWorkerError("CAD manifest GLB identity evidence has unexpected fields")
    if glb.get("preserves_all_component_ids_as_node_names") is not True:
        raise CadWorkerError("CAD manifest reports incomplete GLB node identity")
    if glb.get("observed_component_ids") != list(glb_ids):
        raise CadWorkerError(
            "CAD manifest GLB identity evidence differs from completion"
        )
    if glb.get("observed_extras_mbse_ids") != list(glb_mbse_ids):
        raise CadWorkerError("CAD manifest GLB extras evidence differs from completion")
    if glb.get("preserves_current_viewer_extras_mbse_id") is not True:
        raise CadWorkerError("CAD manifest reports incomplete GLB extras identity")
    if (
        len(glb_mbse_ids) != len(component_ids)
        or set(glb_mbse_ids) != set(component_ids)
    ):
        raise CadWorkerError("CAD manifest GLB extras identities are incomplete")


def _validate_completion(
    output_dir: Path,
    request: Mapping[str, Any],
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    record = _read_json(output_dir / CAD_JOB_RESULT_FILENAME, "completion record")
    if set(record) != _COMPLETION_KEYS:
        raise CadWorkerError("CAD worker completion record has unexpected fields")
    if (
        type(record.get("schema_version")) is not int
        or record["schema_version"] != CAD_JOB_SCHEMA_VERSION
    ):
        raise CadWorkerError(
            "CAD worker completion record has the wrong schema version"
        )
    if record.get("job_id") != request.get("job_id"):
        raise CadWorkerError("CAD worker completion record has the wrong job ID")
    if record.get("status") != "completed":
        raise CadWorkerError("CAD worker did not report completed status")
    backend = _validate_backend(record.get("backend"))

    artifact_values = record.get("artifacts")
    if not isinstance(artifact_values, list) or not all(
        isinstance(item, dict) and set(item) == {"file", "size_bytes"}
        for item in artifact_values
    ):
        raise CadWorkerError("CAD worker completion artifact evidence is malformed")
    artifact_sizes = {
        item["file"]: item["size_bytes"] for item in artifact_values
    }
    if len(artifact_sizes) != len(artifact_values) or set(artifact_sizes) != set(
        CAD_ARTIFACT_FILENAMES
    ):
        raise CadWorkerError("CAD worker completion artifact set is incomplete")
    for filename, recorded_size in artifact_sizes.items():
        path = output_dir / filename
        if type(recorded_size) is not int or recorded_size <= 0:
            raise CadWorkerError(f"CAD worker recorded an invalid size for {filename}")
        if not path.is_file() or path.stat().st_size != recorded_size:
            raise CadWorkerError(
                f"CAD worker artifact {filename} is missing, empty, or changed"
            )

    checks = _mapping(record.get("checks"), "completion checks")
    if set(checks) != {*CAD_REQUIRED_CHECKS, "verified_footprint_extent_mm"}:
        raise CadWorkerError("CAD worker completion checks have unexpected fields")
    if any(checks.get(name) is not True for name in CAD_REQUIRED_CHECKS):
        raise CadWorkerError("CAD worker did not pass every required semantic check")
    if checks.get("verified_footprint_extent_mm") != request.get(
        "expected_footprint_extent_mm"
    ):
        raise CadWorkerError(
            "CAD worker verified the wrong authoritative footprint extent"
        )

    roles = _mapping(
        _mapping(request.get("visualization"), "request visualization").get("roles"),
        "request visualization roles",
    )
    expected_components = tuple(
        _mapping(roles.get(role), f"request role {role}").get("object_id")
        for role in CAD_COMPONENT_ROLES
    )
    if not all(isinstance(item, str) and item for item in expected_components):
        raise CadWorkerError("CAD request component identities are malformed")
    component_ids = _string_list(record.get("component_ids"), "component IDs")
    step_ids = _string_list(record.get("step_component_ids"), "STEP component IDs")
    glb_node_names = _string_list(record.get("glb_node_names"), "GLB node names")
    glb_ids = _string_list(record.get("glb_component_ids"), "GLB component IDs")
    glb_mbse_ids = _string_list(record.get("glb_mbse_ids"), "GLB extras IDs")
    if (
        component_ids != expected_components
        or step_ids != expected_components
        or glb_ids != expected_components
    ):
        raise CadWorkerError(
            "CAD worker did not preserve the exact stable component IDs"
        )
    if not set(expected_components).issubset(glb_node_names):
        raise CadWorkerError("CAD worker GLB node names omit stable component IDs")
    if (
        len(glb_mbse_ids) != len(expected_components)
        or set(glb_mbse_ids) != set(expected_components)
    ):
        raise CadWorkerError(
            "CAD worker did not preserve the exact GLB extras identities"
        )

    glb_path = output_dir / "conceptual-preview.glb"
    try:
        actual_glb = inspect_glb_identity(glb_path)
    except CadExportError as error:
        raise CadWorkerError(f"CAD worker published an invalid GLB: {error}") from error
    actual_glb_ids = tuple(
        object_id
        for object_id in expected_components
        if object_id in actual_glb.node_names
    )
    actual_component_names = tuple(
        name for name in actual_glb.node_names if name in set(expected_components)
    )
    if (
        actual_glb.node_names != glb_node_names
        or actual_glb_ids != glb_ids
        or actual_glb.mbse_ids != glb_mbse_ids
        or len(actual_component_names) != len(expected_components)
        or len(actual_glb.identity_pairs) != len(expected_components)
        or set(actual_glb.identity_pairs)
        != {(object_id, object_id) for object_id in expected_components}
    ):
        raise CadWorkerError(
            "CAD worker GLB identity evidence differs from the actual GLB"
        )

    manifest = _read_json(output_dir / "cad-manifest.json", "CAD manifest")
    _validate_manifest(
        manifest,
        request,
        backend,
        component_ids,
        step_ids,
        glb_ids,
        glb_mbse_ids,
    )
    return (
        record,
        manifest,
        component_ids,
        step_ids,
        glb_node_names,
        glb_ids,
        glb_mbse_ids,
    )


def _process_output(completed: subprocess.CompletedProcess[str]) -> str:
    details = (completed.stderr or completed.stdout or "").strip()
    return f" Worker output: {details}" if details else ""


def export_project_cad(
    model: Model,
    output_dir: Path,
    *,
    python_executable: str | Path | None = None,
    _platform: str | None = None,
) -> CadExportResult:
    """Validate a project, run isolated CAD, and prove the worker's completion."""

    findings = [*validate_model(model), *validate_visualizations(model)]
    errors = [message for severity, message in findings if severity == "ERROR"]
    if errors:
        raise CadExportError(
            "CAD export blocked by project validation errors: " + "; ".join(errors)
        )

    roles = resolve_visualization_profile(
        model, GARDEN_SHED_PROFILE, GARDEN_SHED_REQUIRED_ROLES
    )
    if roles is None:
        raise CadExportError(
            f"Project does not define the supported {GARDEN_SHED_PROFILE!r} "
            "visualization profile"
        )
    spec = build_garden_shed_visualization_spec(roles)

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    completion_path = output_dir / CAD_JOB_RESULT_FILENAME
    completion_path.unlink(missing_ok=True)
    job_id = str(uuid.uuid4())
    request = build_cad_job_request(spec, output_dir, job_id)

    with tempfile.TemporaryDirectory(
        prefix=".mbse-lite-cad-job-", dir=output_dir
    ) as temp:
        request_path = Path(temp) / "request.json"
        request_path.write_text(
            json.dumps(request, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        command = [
            str(python_executable or sys.executable),
            "-m",
            "mbse_lite.cad.worker",
            str(request_path),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            raise CadWorkerError(
                f"Cannot launch isolated CAD worker: {error}"
            ) from error

    try:
        (
            _record,
            manifest,
            component_ids,
            step_ids,
            glb_node_names,
            glb_ids,
            glb_mbse_ids,
        ) = _validate_completion(output_dir, request)
    except CadWorkerError as error:
        raise CadWorkerError(f"{error}.{_process_output(completed)}") from error

    warning: str | None = None
    platform_name = sys.platform if _platform is None else _platform
    if completed.returncode == 0:
        pass
    elif platform_name.startswith("win") and is_windows_heap_corruption_exit_code(
        completed.returncode
    ):
        warning = _KNOWN_WINDOWS_WARNING
    else:
        raise CadWorkerError(
            f"Isolated CAD worker exited with code {completed.returncode}."
            f"{_process_output(completed)}"
        )

    return CadExportResult(
        output_dir=output_dir,
        artifacts=tuple(output_dir / name for name in CAD_ARTIFACT_FILENAMES),
        completion_record=completion_path,
        manifest=dict(manifest),
        component_ids=component_ids,
        step_component_ids=step_ids,
        glb_node_names=glb_node_names,
        glb_component_ids=glb_ids,
        glb_mbse_ids=glb_mbse_ids,
        worker_exit_code=completed.returncode,
        warning=warning,
    )
