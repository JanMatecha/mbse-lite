from __future__ import annotations

import importlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib import metadata
from pathlib import Path
from types import ModuleType
from typing import Any

from ..geometry import GardenShedGeometrySpec, Quantity
from ..visualization.garden_shed import GardenShedVisualizationSpec
from .glb_identity import enrich_glb_identities, inspect_glb_identity
from .protocol import (
    CAD_ARTIFACT_FILENAMES,
    CAD_COMPONENT_ROLES,
    CAD_INSTALL_MESSAGE,
    CadExportError,
    CadGeometryError,
    CadJob,
    CadQueryUnavailableError,
    decimal_text,
    quantity_to_millimetres,
)


CAD_SCHEMA_VERSION = "0.6"
_D = Decimal


@dataclass(frozen=True, slots=True)
class FootprintCadModel:
    """Zero-thickness engineering footprint and its traced domain dimensions."""

    shape: Any
    length_mm: Decimal
    depth_mm: Decimal
    source_object_id: str


@dataclass(frozen=True, slots=True)
class ConceptualCadPreview:
    """Non-authoritative CadQuery assembly built from visualization defaults."""

    assembly: Any
    component_ids: tuple[str, ...]
    authoritative_length_mm: Decimal
    authoritative_depth_mm: Decimal


@dataclass(frozen=True, slots=True)
class BackendCadExportResult:
    """Worker-side artifacts plus semantic evidence checked before completion."""

    output_dir: Path
    artifacts: tuple[Path, ...]
    manifest: dict[str, object]
    component_ids: tuple[str, ...]
    step_component_ids: tuple[str, ...]
    glb_node_names: tuple[str, ...]
    glb_component_ids: tuple[str, ...]
    glb_mbse_ids: tuple[str, ...]
    checks: dict[str, object]


def _load_cadquery() -> ModuleType:
    """Load the optional backend only when a CAD operation is requested."""

    try:
        return importlib.import_module("cadquery")
    except (ImportError, OSError) as error:
        raise CadQueryUnavailableError(CAD_INSTALL_MESSAGE) from error


def _visualization_metres_to_millimetres(value: float, name: str) -> Decimal:
    """Convert a labeled visualization-only metre value at the same unit boundary."""

    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as error:
        raise CadGeometryError(
            f"Visualization-only CAD value {name!r} is not numeric"
        ) from error
    if not decimal_value.is_finite() or decimal_value <= 0:
        raise CadGeometryError(
            f"Visualization-only CAD value {name!r} must be finite and positive"
        )
    return decimal_value * Decimal("1000")


def _cad_float(value_mm: Decimal) -> float:
    """Make the only Decimal-to-float conversion, immediately at a CadQuery call."""

    value = float(value_mm)
    if not math.isfinite(value):
        raise CadGeometryError(
            "A millimetre value is outside the CadQuery numeric range"
        )
    return value


def _box(
    cq: ModuleType,
    size: tuple[Decimal, Decimal, Decimal],
    center: tuple[Decimal, Decimal, Decimal],
    *,
    rotate_x_degrees: float | None = None,
) -> Any:
    workplane = cq.Workplane("XY").box(
        *(_cad_float(value) for value in size),
        centered=(True, True, True),
    )
    center_float = tuple(_cad_float(value) for value in center)
    workplane = workplane.translate(center_float)
    if rotate_x_degrees is not None:
        axis_end = (center_float[0] + 1.0, center_float[1], center_float[2])
        workplane = workplane.rotate(center_float, axis_end, rotate_x_degrees)
    return workplane.val()


def build_authoritative_footprint(
    geometry: GardenShedGeometrySpec,
    *,
    _cadquery: ModuleType | None = None,
) -> FootprintCadModel:
    """Build a planar face from only the two authoritative footprint dimensions."""

    length_mm = quantity_to_millimetres(geometry.external_length)
    depth_mm = quantity_to_millimetres(geometry.external_depth)
    cq = _cadquery or _load_cadquery()
    outer_wire = (
        cq.Workplane("XY")
        .rect(_cad_float(length_mm), _cad_float(depth_mm))
        .val()
    )
    face = cq.Face.makeFromWires(outer_wire)
    return FootprintCadModel(
        shape=face,
        length_mm=length_mm,
        depth_mm=depth_mm,
        source_object_id=geometry.source_object_id,
    )


def build_conceptual_preview(
    spec: GardenShedVisualizationSpec,
    *,
    _cadquery: ModuleType | None = None,
) -> ConceptualCadPreview:
    """Build a visualization-only assembly with stable MBSE IDs as child names."""

    length = quantity_to_millimetres(spec.geometry.external_length)
    depth = quantity_to_millimetres(spec.geometry.external_depth)
    height = _visualization_metres_to_millimetres(
        spec.conceptual_height, "conceptual_height"
    )
    wall = _visualization_metres_to_millimetres(spec.wall_thickness, "wall_thickness")
    floor = _visualization_metres_to_millimetres(
        spec.floor_thickness, "floor_thickness"
    )
    door_height = _visualization_metres_to_millimetres(
        spec.door_height, "door_height"
    )
    shelving_height = _visualization_metres_to_millimetres(
        spec.shelving_height, "shelving_height"
    )
    ramp_length = _visualization_metres_to_millimetres(
        spec.ramp_length, "ramp_length"
    )

    half = _D("0.5")
    left = -length * half
    right = length * half
    front = depth * half
    rear = -depth * half
    mower_length = length * Decimal(str(spec.mower_fraction))
    split = left + mower_length
    main_length = length - mower_length
    zone_depth = max(depth - 2 * wall, depth * _D("0.8"))
    main_door_left = left + length * Decimal(str(spec.main_door_start))
    main_door_width = length * Decimal(str(spec.main_door_fraction))
    main_leaf_width = max(main_door_width * half - _D("15"), _D("50"))
    mower_door_left = left + mower_length * Decimal(str(spec.mower_door_start))
    mower_door_width = mower_length * Decimal(str(spec.mower_door_fraction))
    door_y = front + wall * half
    door_z = floor + door_height * half
    ramp_rise = floor * 2
    ramp_angle = math.degrees(
        math.atan2(_cad_float(ramp_rise), _cad_float(ramp_length))
    )
    cq = _cadquery or _load_cadquery()

    shapes_by_role: dict[str, list[Any]] = {
        "enclosure": [
            _box(
                cq,
                (length, wall, height),
                (_D("0"), rear + wall * half, height * half),
            ),
            _box(
                cq,
                (wall, depth, height),
                (left + wall * half, _D("0"), height * half),
            ),
            _box(
                cq,
                (wall, depth, height),
                (right - wall * half, _D("0"), height * half),
            ),
            _box(
                cq,
                (length, wall, floor * 2),
                (_D("0"), front - wall * half, floor),
            ),
        ],
        "main_storage": [
            _box(
                cq,
                (max(main_length - 2 * wall, wall), zone_depth, floor),
                (split + main_length * half, _D("0"), floor * half),
            )
        ],
        "mower_compartment": [
            _box(
                cq,
                (max(mower_length - 2 * wall, wall), zone_depth, floor),
                (left + mower_length * half, _D("0"), floor * half),
            ),
            _box(
                cq,
                (wall, depth, height * _D("0.9")),
                (split, _D("0"), height * _D("0.45")),
            ),
        ],
        "main_door": [
            _box(
                cq,
                (main_leaf_width, wall, door_height),
                (main_door_left + main_leaf_width * half, door_y, door_z),
            ),
            _box(
                cq,
                (main_leaf_width, wall, door_height),
                (
                    main_door_left + main_door_width - main_leaf_width * half,
                    door_y,
                    door_z,
                ),
            ),
        ],
        "mower_door": [
            _box(
                cq,
                (mower_door_width, wall, door_height),
                (mower_door_left + mower_door_width * half, door_y, door_z),
            )
        ],
        "mower_ramp": [
            _box(
                cq,
                (mower_door_width * _D("1.08"), ramp_length, floor * _D("0.55")),
                (
                    mower_door_left + mower_door_width * half,
                    front + ramp_length * half,
                    ramp_rise * half,
                ),
                rotate_x_degrees=ramp_angle,
            )
        ],
        "shelving": [
            _box(
                cq,
                (
                    length * Decimal(str(spec.shelving_fraction)),
                    depth * _D("0.72"),
                    shelving_height,
                ),
                (
                    right
                    - length * Decimal(str(spec.shelving_fraction)) * half,
                    _D("0"),
                    floor + shelving_height * half,
                ),
            )
        ],
    }
    colors = {
        "enclosure": (0.18, 0.27, 0.36, 0.30),
        "main_storage": (0.40, 0.63, 0.88, 0.48),
        "mower_compartment": (0.43, 0.67, 0.34, 0.52),
        "main_door": (0.50, 0.35, 0.78, 1.0),
        "mower_door": (0.08, 0.50, 0.55, 1.0),
        "mower_ramp": (0.35, 0.72, 0.75, 0.85),
        "shelving": (0.82, 0.55, 0.15, 0.72),
    }

    assembly = cq.Assembly(name="conceptual-preview")
    component_ids: list[str] = []
    for role in CAD_COMPONENT_ROLES:
        object_id = spec.roles[role].id
        component_ids.append(object_id)
        compound = cq.Compound.makeCompound(shapes_by_role[role])
        assembly.add(compound, name=object_id, color=cq.Color(*colors[role]))

    return ConceptualCadPreview(
        assembly=assembly,
        component_ids=tuple(component_ids),
        authoritative_length_mm=length,
        authoritative_depth_mm=depth,
    )


def inspect_glb_node_names(path: Path) -> tuple[str, ...]:
    """Read stable-name evidence from a binary glTF JSON chunk."""

    return inspect_glb_identity(path).node_names


def inspect_glb_mbse_ids(path: Path) -> tuple[str, ...]:
    """Read IDs using the existing viewer's ``node.extras.mbse_id`` contract."""

    return inspect_glb_identity(path).mbse_ids


def inspect_step_object_names(
    path: Path, *, _cadquery: ModuleType | None = None
) -> tuple[str, ...]:
    """Re-import a STEP assembly and return its semantic object names."""

    cq = _cadquery or _load_cadquery()
    assembly = cq.Assembly.load(str(path))
    return tuple(assembly.objects)


def _quantity_manifest(quantity: Quantity) -> dict[str, object]:
    return {
        "value": str(quantity.value),
        "unit": quantity.unit,
        "source": quantity.source.to_dict(),
    }


def _observed_ids(names: tuple[str, ...], expected: tuple[str, ...]) -> tuple[str, ...]:
    names = set(names)
    return tuple(object_id for object_id in expected if object_id in names)


def _manifest(
    cq: ModuleType,
    spec: GardenShedVisualizationSpec,
    footprint: FootprintCadModel,
    preview: ConceptualCadPreview,
    step_ids: tuple[str, ...],
    glb_ids: tuple[str, ...],
    glb_mbse_ids: tuple[str, ...],
) -> dict[str, object]:
    try:
        cadquery_version = metadata.version("cadquery")
    except metadata.PackageNotFoundError:
        cadquery_version = str(getattr(cq, "__version__", "unknown"))

    conceptual_sources = [
        footprint.source_object_id,
        *preview.component_ids,
        *spec.displayed_candidate_ids,
    ]
    return {
        "schema_version": CAD_SCHEMA_VERSION,
        "generated_metadata": True,
        "source_of_truth": "project Markdown",
        "backend": {
            "name": "cadquery",
            "version": cadquery_version,
            "internal_length_unit": "mm",
        },
        "artifacts": [
            {
                "file": "footprint.step",
                "format": "STEP",
                "authority": "engineering",
                "scope": "footprint-only",
                "source_object_ids": [footprint.source_object_id],
                "extent_mm": {
                    "x": decimal_text(footprint.length_mm),
                    "y": decimal_text(footprint.depth_mm),
                    "z": "0",
                },
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
            "source_object_id": footprint.source_object_id,
            "external_length": _quantity_manifest(spec.geometry.external_length),
            "external_depth": _quantity_manifest(spec.geometry.external_depth),
        },
        "visualization_only_inputs": {
            "conceptual_height_m": spec.conceptual_height,
            "wall_thickness_m": spec.wall_thickness,
            "floor_thickness_m": spec.floor_thickness,
            "door_height_m": spec.door_height,
            "shelving_height_m": spec.shelving_height,
            "ramp_length_m": spec.ramp_length,
            "mower_fraction": spec.mower_fraction,
            "shelving_fraction": spec.shelving_fraction,
            "main_door_start": spec.main_door_start,
            "main_door_fraction": spec.main_door_fraction,
            "mower_door_start": spec.mower_door_start,
            "mower_door_fraction": spec.mower_door_fraction,
        },
        "stable_identity": {
            "in_memory_component_names": list(preview.component_ids),
            "step": {
                "preserves_all_component_ids": set(step_ids)
                == set(preview.component_ids),
                "observed_component_ids": list(step_ids),
            },
            "glb": {
                "preserves_all_component_ids_as_node_names": set(glb_ids)
                == set(preview.component_ids),
                "observed_component_ids": list(glb_ids),
                "preserves_current_viewer_extras_mbse_id": set(glb_mbse_ids)
                == set(preview.component_ids),
                "observed_extras_mbse_ids": list(glb_mbse_ids),
            },
        },
    }


def _extent(shape: Any) -> tuple[float, float, float]:
    bounds = shape.BoundingBox()
    return bounds.xlen, bounds.ylen, bounds.zlen


def _extent_matches(
    actual: tuple[float, float, float], expected: Any
) -> bool:
    expected_values = tuple(float(expected[axis]) for axis in ("x", "y", "z"))
    return all(
        math.isclose(observed, wanted, rel_tol=1e-9, abs_tol=1e-6)
        for observed, wanted in zip(actual, expected_values, strict=True)
    )


def execute_cad_job(job: CadJob) -> BackendCadExportResult:
    """Execute one validated worker job and verify its outputs semantically."""

    spec = job.visualization_spec
    output_dir = job.output_dir
    cq = _load_cadquery()
    footprint = build_authoritative_footprint(spec.geometry, _cadquery=cq)
    preview = build_conceptual_preview(spec, _cadquery=cq)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    names = CAD_ARTIFACT_FILENAMES
    with tempfile.TemporaryDirectory(prefix=".mbse-lite-cad-", dir=output_dir) as temp:
        temporary = Path(temp)
        footprint_path = temporary / names[0]
        conceptual_step_path = temporary / names[1]
        conceptual_glb_path = temporary / names[2]
        manifest_path = temporary / names[3]

        footprint.shape.export(str(footprint_path), "STEP", unit="MM")
        preview.assembly.export(
            str(conceptual_step_path), "STEP", mode="default", unit="MM"
        )
        preview.assembly.export(str(conceptual_glb_path))

        for path in (footprint_path, conceptual_step_path, conceptual_glb_path):
            if not path.is_file() or path.stat().st_size <= 0:
                raise CadExportError(f"CadQuery did not create a non-empty {path.name}")

        enrich_glb_identities(
            conceptual_glb_path,
            {object_id: object_id for object_id in preview.component_ids},
        )

        imported_footprint = cq.importers.importStep(
            str(footprint_path), unit="MM"
        ).val()
        imported_extent = _extent(imported_footprint)
        if not _extent_matches(imported_extent, job.expected_footprint_extent_mm):
            raise CadExportError(
                "Re-imported authoritative footprint extent does not match the CAD job"
            )
        if not math.isclose(imported_extent[2], 0.0, rel_tol=0.0, abs_tol=1e-6):
            raise CadExportError("Re-imported authoritative footprint is not planar")

        step_object_names = inspect_step_object_names(
            conceptual_step_path, _cadquery=cq
        )
        step_ids = _observed_ids(step_object_names, preview.component_ids)
        glb_node_names = inspect_glb_node_names(conceptual_glb_path)
        glb_ids = _observed_ids(glb_node_names, preview.component_ids)
        glb_mbse_ids = inspect_glb_mbse_ids(conceptual_glb_path)
        if set(step_ids) != set(preview.component_ids):
            raise CadExportError(
                "STEP export did not preserve every stable component ID"
            )
        if set(glb_ids) != set(preview.component_ids):
            raise CadExportError(
                "GLB node names did not preserve every stable component ID"
            )
        if (
            len(glb_mbse_ids) != len(preview.component_ids)
            or set(glb_mbse_ids) != set(preview.component_ids)
        ):
            raise CadExportError(
                "GLB extras did not preserve every stable component ID"
            )
        manifest = _manifest(
            cq, spec, footprint, preview, step_ids, glb_ids, glb_mbse_ids
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if not manifest_path.is_file() or manifest_path.stat().st_size <= 0:
            raise CadExportError("CadQuery did not create a non-empty CAD manifest")

        for name in names:
            os.replace(temporary / name, output_dir / name)

    artifacts = tuple(output_dir / name for name in names)
    if not all(path.is_file() and path.stat().st_size > 0 for path in artifacts):
        raise CadExportError("One or more final CAD artifacts are missing or empty")
    checks: dict[str, object] = {
        "authoritative_footprint_step_readable": True,
        "authoritative_footprint_extent_matches_request": True,
        "authoritative_footprint_zero_z_extent": True,
        "manifest_complete": True,
        "conceptual_artifacts_complete": True,
        "component_identity_checks_complete": True,
        "required_artifacts_nonempty": True,
        "verified_footprint_extent_mm": dict(job.expected_footprint_extent_mm),
    }
    return BackendCadExportResult(
        output_dir=output_dir,
        artifacts=artifacts,
        manifest=manifest,
        component_ids=preview.component_ids,
        step_component_ids=step_ids,
        glb_node_names=glb_node_names,
        glb_component_ids=glb_ids,
        glb_mbse_ids=glb_mbse_ids,
        checks=checks,
    )
