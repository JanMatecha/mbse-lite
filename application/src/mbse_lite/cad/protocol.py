from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from ..core import ModelObject, SourceRef
from ..geometry import GardenShedGeometrySpec, Quantity
from ..visualization.garden_shed import GardenShedVisualizationSpec


CAD_JOB_SCHEMA_VERSION = 1
CAD_JOB_RESULT_FILENAME = "cad-job-result.json"
CAD_ARTIFACT_FILENAMES = (
    "footprint.step",
    "conceptual-preview.step",
    "conceptual-preview.glb",
    "cad-manifest.json",
)
CAD_COMPONENT_ROLES = (
    "enclosure",
    "main_storage",
    "mower_compartment",
    "main_door",
    "mower_door",
    "mower_ramp",
    "shelving",
)
CAD_REQUIRED_CHECKS = (
    "authoritative_footprint_step_readable",
    "authoritative_footprint_extent_matches_request",
    "authoritative_footprint_zero_z_extent",
    "manifest_complete",
    "conceptual_artifacts_complete",
    "component_identity_checks_complete",
    "required_artifacts_nonempty",
)
WINDOWS_HEAP_CORRUPTION_NTSTATUS = 0xC0000374
WINDOWS_HEAP_CORRUPTION_SIGNED = -1073740940
CAD_INSTALL_MESSAGE = (
    "CadQuery support is not installed.\n"
    "Install the optional CAD dependencies with: uv sync --extra cad"
)
_UNIT_TO_MILLIMETRES = {
    "mm": Decimal("1"),
    "m": Decimal("1000"),
}


class CadError(RuntimeError):
    """Base class for concise user-facing CAD failures."""


class CadQueryUnavailableError(CadError):
    """The optional CadQuery runtime cannot be imported by the worker."""


class CadGeometryError(CadError):
    """A value is unsafe at the CAD unit or geometry boundary."""


class CadExportError(CadError):
    """A CAD backend operation could not complete safely."""


class CadWorkerError(CadError):
    """The isolated worker did not prove successful completion."""


@dataclass(frozen=True, slots=True)
class CadJob:
    job_id: str
    output_dir: Path
    visualization_spec: GardenShedVisualizationSpec
    expected_footprint_extent_mm: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CadExportResult:
    output_dir: Path
    artifacts: tuple[Path, ...]
    completion_record: Path
    manifest: dict[str, object]
    component_ids: tuple[str, ...]
    step_component_ids: tuple[str, ...]
    glb_node_names: tuple[str, ...]
    glb_component_ids: tuple[str, ...]
    glb_mbse_ids: tuple[str, ...]
    worker_exit_code: int
    warning: str | None = None


def quantity_to_millimetres(quantity: Quantity) -> Decimal:
    """Validate and convert one authoritative Quantity to exact millimetres."""

    factor = _UNIT_TO_MILLIMETRES.get(quantity.unit)
    if factor is None:
        supported = ", ".join(sorted(_UNIT_TO_MILLIMETRES))
        raise CadGeometryError(
            f"Unsupported CAD length unit {quantity.unit!r}; "
            f"supported units: {supported}"
        )
    if not isinstance(quantity.value, Decimal):
        raise CadGeometryError("CAD quantities must use Decimal values")
    if not quantity.value.is_finite() or quantity.value <= 0:
        raise CadGeometryError("CAD quantities must be finite and positive")
    return quantity.value * factor


def decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _quantity_to_dict(quantity: Quantity) -> dict[str, object]:
    return {
        "value": str(quantity.value),
        "unit": quantity.unit,
        "source": quantity.source.to_dict(),
    }


def build_cad_job_request(
    spec: GardenShedVisualizationSpec,
    output_dir: Path,
    job_id: str,
) -> dict[str, object]:
    length_mm = quantity_to_millimetres(spec.geometry.external_length)
    depth_mm = quantity_to_millimetres(spec.geometry.external_depth)
    return {
        "schema_version": CAD_JOB_SCHEMA_VERSION,
        "job_type": "garden-shed-cad-export",
        "job_id": job_id,
        "output_dir": str(Path(output_dir).resolve()),
        "geometry": {
            "source_object_id": spec.geometry.source_object_id,
            "external_length": _quantity_to_dict(spec.geometry.external_length),
            "external_depth": _quantity_to_dict(spec.geometry.external_depth),
        },
        "expected_footprint_extent_mm": {
            "x": decimal_text(length_mm),
            "y": decimal_text(depth_mm),
            "z": "0",
        },
        "visualization": {
            "roles": {
                role: {"object_id": obj.id, "object_type": obj.type}
                for role, obj in spec.roles.items()
            },
            "footprint_note": spec.footprint_note,
            "displayed_candidate_ids": list(spec.displayed_candidate_ids),
            "candidate_note": spec.candidate_note,
            "defaults": {
                "mower_fraction": spec.mower_fraction,
                "shelving_fraction": spec.shelving_fraction,
                "main_door_start": spec.main_door_start,
                "main_door_fraction": spec.main_door_fraction,
                "mower_door_start": spec.mower_door_start,
                "mower_door_fraction": spec.mower_door_fraction,
                "conceptual_height": spec.conceptual_height,
                "wall_thickness": spec.wall_thickness,
                "floor_thickness": spec.floor_thickness,
                "door_height": spec.door_height,
                "shelving_height": spec.shelving_height,
                "ramp_length": spec.ramp_length,
            },
        },
    }


def _quantity_from_dict(value: object) -> Quantity:
    if not isinstance(value, dict):
        raise CadExportError("CAD job quantity must be an object")
    source = value.get("source")
    if not isinstance(source, dict):
        raise CadExportError("CAD job quantity is missing source provenance")
    try:
        quantity = Quantity(
            value=Decimal(str(value["value"])),
            unit=str(value["unit"]),
            source=SourceRef(
                file=str(source["file"]),
                table_index=int(source["table_index"]),
                row_index=(
                    None
                    if source.get("row_index") is None
                    else int(source["row_index"])
                ),
                row_id=(
                    None if source.get("row_id") is None else str(source["row_id"])
                ),
                column=(
                    None if source.get("column") is None else str(source["column"])
                ),
                line=None if source.get("line") is None else int(source["line"]),
            ),
        )
    except (InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise CadExportError("CAD job quantity is malformed") from error
    quantity_to_millimetres(quantity)
    return quantity


def parse_cad_job_request(value: object) -> CadJob:
    if not isinstance(value, dict):
        raise CadExportError("CAD job request must be a JSON object")
    if value.get("schema_version") != CAD_JOB_SCHEMA_VERSION:
        raise CadExportError("Unsupported CAD job request schema")
    if value.get("job_type") != "garden-shed-cad-export":
        raise CadExportError("Unsupported CAD job type")
    job_id = value.get("job_id")
    output_dir = value.get("output_dir")
    geometry = value.get("geometry")
    visualization = value.get("visualization")
    expected_extent = value.get("expected_footprint_extent_mm")
    if not isinstance(job_id, str) or not job_id:
        raise CadExportError("CAD job request has no job ID")
    if not isinstance(output_dir, str) or not output_dir:
        raise CadExportError("CAD job request has no output directory")
    if not isinstance(geometry, dict) or not isinstance(visualization, dict):
        raise CadExportError(
            "CAD job request is missing geometry or visualization data"
        )
    if not isinstance(expected_extent, dict):
        raise CadExportError("CAD job request is missing its expected footprint extent")

    external_length = _quantity_from_dict(geometry.get("external_length"))
    external_depth = _quantity_from_dict(geometry.get("external_depth"))
    source_object_id = geometry.get("source_object_id")
    if not isinstance(source_object_id, str) or not source_object_id:
        raise CadExportError("CAD job geometry has no source object ID")
    calculated_extent = {
        "x": decimal_text(quantity_to_millimetres(external_length)),
        "y": decimal_text(quantity_to_millimetres(external_depth)),
        "z": "0",
    }
    normalized_extent = {
        key: str(expected_extent.get(key, "")) for key in ("x", "y", "z")
    }
    if normalized_extent != calculated_extent:
        raise CadExportError(
            "CAD job expected footprint extent does not match its quantities"
        )

    role_values = visualization.get("roles")
    defaults = visualization.get("defaults")
    if not isinstance(role_values, dict) or not isinstance(defaults, dict):
        raise CadExportError("CAD job visualization roles or defaults are malformed")
    roles: dict[str, ModelObject] = {}
    try:
        for role, item in role_values.items():
            if not isinstance(role, str) or not isinstance(item, dict):
                raise TypeError
            roles[role] = ModelObject(
                id=str(item["object_id"]),
                type=str(item["object_type"]),
            )
        missing_roles = sorted(set(CAD_COMPONENT_ROLES) - set(roles))
        if missing_roles:
            raise CadExportError(
                "CAD job is missing component roles: " + ", ".join(missing_roles)
            )
        geometry_spec = GardenShedGeometrySpec(
            source_object_id=source_object_id,
            external_length=external_length,
            external_depth=external_depth,
        )
        spec = GardenShedVisualizationSpec(
            roles=roles,
            geometry=geometry_spec,
            footprint_note=str(visualization.get("footprint_note", "")),
            displayed_candidate_ids=tuple(
                str(item) for item in visualization.get("displayed_candidate_ids", [])
            ),
            candidate_note=str(visualization.get("candidate_note", "")),
            **{name: float(defaults[name]) for name in (
                "mower_fraction",
                "shelving_fraction",
                "main_door_start",
                "main_door_fraction",
                "mower_door_start",
                "mower_door_fraction",
                "conceptual_height",
                "wall_thickness",
                "floor_thickness",
                "door_height",
                "shelving_height",
                "ramp_length",
            )},
        )
    except CadExportError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise CadExportError("CAD job visualization data is malformed") from error

    return CadJob(
        job_id=job_id,
        output_dir=Path(output_dir),
        visualization_spec=spec,
        expected_footprint_extent_mm=calculated_extent,
    )


def is_windows_heap_corruption_exit_code(exit_code: int) -> bool:
    return exit_code in {
        WINDOWS_HEAP_CORRUPTION_NTSTATUS,
        WINDOWS_HEAP_CORRUPTION_SIGNED,
    }
