from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .glb_identity import inspect_glb_identity
from .protocol import (
    CAD_ARTIFACT_FILENAMES,
    CAD_JOB_RESULT_FILENAME,
    CAD_JOB_SCHEMA_VERSION,
    CAD_REQUIRED_CHECKS,
    CadExportError,
    CadWorkerError,
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
_MANIFEST_KEYS = {
    "schema_version",
    "generated_metadata",
    "source_of_truth",
    "backend",
    "artifacts",
    "engineering_inputs",
    "visualization_only_inputs",
    "stable_identity",
}


@dataclass(frozen=True, slots=True)
class CadPreviewAsset:
    """Validated, dependency-free input for the static production viewer."""

    data: bytes
    source_unit: str
    viewer_scale: float
    component_ids: tuple[str, ...]


def unit_scale_to_m(source_unit: str) -> float:
    """Return the explicit conversion from a supported source unit to metres."""

    scales = {"m": 1.0, "mm": 0.001}
    try:
        return scales[source_unit]
    except KeyError as error:
        supported = ", ".join(sorted(scales))
        raise CadWorkerError(
            f"Unsupported CAD preview length unit {source_unit!r}; "
            f"supported units: {supported}"
        ) from error


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CadWorkerError(f"CAD preview {label} must be a JSON object")
    return value


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise CadWorkerError(f"CAD preview {label} must be a list of non-empty strings")
    values = tuple(value)
    if len(values) != len(set(values)):
        raise CadWorkerError(f"CAD preview {label} contains duplicate identities")
    return values


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CadWorkerError(f"CAD preview is missing {label}: {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CadWorkerError(f"CAD preview has an invalid {label}: {error}") from error
    return _mapping(value, label)


def validate_cad_preview(
    preview_dir: str | Path,
    *,
    model_object_ids: set[str] | None = None,
    expected_component_ids: tuple[str, ...] | None = None,
) -> CadPreviewAsset:
    """Validate completed CAD evidence and return the conceptual GLB for packaging.

    This consumer-side validation intentionally uses only JSON, filesystem and the
    dependency-free GLB parser. It never imports or invokes CadQuery/OCP.
    """

    directory = Path(preview_dir)
    if not directory.is_dir():
        raise CadWorkerError(f"CAD preview directory does not exist: {directory}")

    completion = _read_json(
        directory / CAD_JOB_RESULT_FILENAME, "completion record"
    )
    if set(completion) != _COMPLETION_KEYS:
        raise CadWorkerError("CAD preview completion record has unexpected fields")
    if completion.get("schema_version") != CAD_JOB_SCHEMA_VERSION:
        raise CadWorkerError("CAD preview completion record has the wrong schema version")
    if not isinstance(completion.get("job_id"), str) or not completion["job_id"]:
        raise CadWorkerError("CAD preview completion record has no job ID")
    if completion.get("status") != "completed":
        raise CadWorkerError("CAD preview completion record is not completed")

    backend = _mapping(completion.get("backend"), "backend metadata")
    if set(backend) != {"name", "version", "internal_length_unit"}:
        raise CadWorkerError("CAD preview backend metadata has unexpected fields")
    if backend.get("name") != "cadquery":
        raise CadWorkerError("CAD preview completion does not report CadQuery")
    if not isinstance(backend.get("version"), str) or not backend["version"]:
        raise CadWorkerError("CAD preview completion has no backend version")
    source_unit = backend.get("internal_length_unit")
    if not isinstance(source_unit, str):
        raise CadWorkerError("CAD preview completion has no internal length unit")
    viewer_scale = unit_scale_to_m(source_unit)

    artifact_values = completion.get("artifacts")
    if not isinstance(artifact_values, list) or not all(
        isinstance(item, dict) and set(item) == {"file", "size_bytes"}
        for item in artifact_values
    ):
        raise CadWorkerError("CAD preview completion artifact evidence is malformed")
    artifact_sizes = {item["file"]: item["size_bytes"] for item in artifact_values}
    if len(artifact_sizes) != len(artifact_values) or set(artifact_sizes) != set(
        CAD_ARTIFACT_FILENAMES
    ):
        raise CadWorkerError("CAD preview completion artifact set is incomplete")
    for filename, recorded_size in artifact_sizes.items():
        path = directory / filename
        if type(recorded_size) is not int or recorded_size <= 0:
            raise CadWorkerError(f"CAD preview recorded an invalid size for {filename}")
        if not path.is_file() or path.stat().st_size != recorded_size:
            raise CadWorkerError(
                f"CAD preview artifact {filename} is missing, empty, or changed"
            )

    checks = _mapping(completion.get("checks"), "completion checks")
    if set(checks) != {*CAD_REQUIRED_CHECKS, "verified_footprint_extent_mm"}:
        raise CadWorkerError("CAD preview completion checks have unexpected fields")
    if any(checks.get(name) is not True for name in CAD_REQUIRED_CHECKS):
        raise CadWorkerError("CAD preview did not pass every required semantic check")

    component_ids = _string_list(completion.get("component_ids"), "component IDs")
    if not component_ids:
        raise CadWorkerError("CAD preview has no component identities")
    if expected_component_ids is not None and component_ids != expected_component_ids:
        raise CadWorkerError(
            "CAD preview component identities differ from the project's generated view"
        )
    if model_object_ids is not None and not set(component_ids).issubset(model_object_ids):
        unknown = sorted(set(component_ids) - model_object_ids)
        raise CadWorkerError(
            "CAD preview identities are not present in the project model: "
            + ", ".join(unknown)
        )
    glb_names = _string_list(completion.get("glb_node_names"), "GLB node names")
    step_component_ids = _string_list(
        completion.get("step_component_ids"), "STEP component IDs"
    )
    glb_component_ids = _string_list(
        completion.get("glb_component_ids"), "GLB component IDs"
    )
    glb_mbse_ids = _string_list(completion.get("glb_mbse_ids"), "GLB extras IDs")
    if (
        step_component_ids != component_ids
        or glb_component_ids != component_ids
        or glb_mbse_ids != component_ids
    ):
        raise CadWorkerError("CAD preview completion has incomplete component identity evidence")
    if not set(component_ids).issubset(glb_names):
        raise CadWorkerError("CAD preview completion omits component node names")

    manifest = _read_json(directory / "cad-manifest.json", "CAD manifest")
    if set(manifest) != _MANIFEST_KEYS:
        raise CadWorkerError("CAD preview manifest has unexpected or missing fields")
    if manifest.get("schema_version") != "0.6":
        raise CadWorkerError("CAD preview manifest has the wrong schema version")
    if manifest.get("generated_metadata") is not True:
        raise CadWorkerError("CAD preview manifest is not generated metadata")
    if manifest.get("source_of_truth") != "project Markdown":
        raise CadWorkerError("CAD preview manifest changed the source-of-truth declaration")
    if manifest.get("backend") != backend:
        raise CadWorkerError("CAD preview completion and manifest backend metadata differ")

    manifest_artifacts = manifest.get("artifacts")
    if not isinstance(manifest_artifacts, list) or not all(
        isinstance(item, dict) for item in manifest_artifacts
    ):
        raise CadWorkerError("CAD preview manifest artifact classifications are malformed")
    if len(manifest_artifacts) != 3 or {
        item.get("file") for item in manifest_artifacts
    } != {"footprint.step", "conceptual-preview.step", "conceptual-preview.glb"}:
        raise CadWorkerError("CAD preview manifest artifact classifications are incomplete")
    conceptual_entries = [
        item for item in manifest_artifacts if item.get("file") == "conceptual-preview.glb"
    ]
    if len(conceptual_entries) != 1:
        raise CadWorkerError("CAD preview manifest does not classify conceptual-preview.glb")
    conceptual = conceptual_entries[0]
    if conceptual.get("format") != "GLB":
        raise CadWorkerError("CAD preview manifest classifies the preview with the wrong format")
    if conceptual.get("authority") != "visualization-only":
        raise CadWorkerError("CAD preview manifest must report visualization-only authority")
    if conceptual.get("scope") != "conceptual-preview":
        raise CadWorkerError("CAD preview manifest must report conceptual-preview scope")

    stable = _mapping(manifest.get("stable_identity"), "manifest identity evidence")
    if set(stable) != {"in_memory_component_names", "step", "glb"}:
        raise CadWorkerError("CAD preview manifest identity evidence has unexpected fields")
    if stable.get("in_memory_component_names") != list(component_ids):
        raise CadWorkerError("CAD preview manifest component identities differ from completion")
    step_evidence = _mapping(stable.get("step"), "manifest STEP identity evidence")
    if step_evidence != {
        "preserves_all_component_ids": True,
        "observed_component_ids": list(component_ids),
    }:
        raise CadWorkerError("CAD preview manifest STEP identity evidence is incomplete")
    glb_evidence = _mapping(stable.get("glb"), "manifest GLB identity evidence")
    if set(glb_evidence) != {
        "preserves_all_component_ids_as_node_names",
        "observed_component_ids",
        "preserves_current_viewer_extras_mbse_id",
        "observed_extras_mbse_ids",
    }:
        raise CadWorkerError("CAD preview manifest GLB identity evidence has unexpected fields")
    if (
        glb_evidence.get("preserves_all_component_ids_as_node_names") is not True
        or glb_evidence.get("observed_component_ids") != list(component_ids)
    ):
        raise CadWorkerError("CAD preview manifest GLB node identity evidence is incomplete")
    if glb_evidence.get("preserves_current_viewer_extras_mbse_id") is not True:
        raise CadWorkerError("CAD preview manifest reports incomplete GLB extras identity")
    if glb_evidence.get("observed_extras_mbse_ids") != list(component_ids):
        raise CadWorkerError("CAD preview manifest GLB extras evidence is incomplete")

    glb_path = directory / "conceptual-preview.glb"
    try:
        actual = inspect_glb_identity(glb_path)
    except CadExportError as error:
        raise CadWorkerError(f"CAD preview contains an invalid GLB: {error}") from error
    if (
        actual.node_names != glb_names
        or actual.mbse_ids != component_ids
        or len(actual.identity_pairs) != len(component_ids)
        or set(actual.identity_pairs)
        != {(object_id, object_id) for object_id in component_ids}
    ):
        raise CadWorkerError("CAD preview identity evidence differs from the actual GLB")

    return CadPreviewAsset(
        data=glb_path.read_bytes(),
        source_unit=source_unit,
        viewer_scale=viewer_scale,
        component_ids=component_ids,
    )
