from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .core import ModelObject, SourceRef


class GeometryValueError(ValueError):
    """A structured engineering value cannot safely drive geometry."""


@dataclass(frozen=True, slots=True)
class Quantity:
    """A deterministic engineering quantity traced to one Markdown cell."""

    value: Decimal
    unit: str
    source: SourceRef


@dataclass(frozen=True, slots=True)
class GeometrySpec:
    """Base identity for typed authoritative geometry inputs."""

    source_object_id: str


@dataclass(frozen=True, slots=True)
class GardenShedGeometrySpec(GeometrySpec):
    """Authoritative external envelope inputs for garden-shed geometry."""

    external_length: Quantity
    external_depth: Quantity


def parse_positive_quantity(
    obj: ModelObject,
    attribute_name: str,
    *,
    expected_unit: str,
    expected_object_type: str,
) -> Quantity:
    """Read ``Name [unit]`` from an object and validate it for geometry use."""

    if obj.type != expected_object_type:
        raise GeometryValueError(
            f"Geometry source {obj.id} has type {obj.type!r}; "
            f"expected {expected_object_type!r}"
        )

    column_pattern = re.compile(rf"^{re.escape(attribute_name)}\s*\[([^\]]+)\]$")
    matching_columns = [
        (column, match.group(1).strip())
        for column in obj.attributes
        if (match := column_pattern.fullmatch(column)) is not None
    ]
    if not matching_columns:
        raise GeometryValueError(
            f"Geometry source {obj.id} is missing required value "
            f"{attribute_name!r} with unit [{expected_unit}]"
        )
    if len(matching_columns) > 1:
        raise GeometryValueError(
            f"Geometry source {obj.id} defines {attribute_name!r} more than once"
        )
    column, unit = matching_columns[0]
    if unit != expected_unit:
        raise GeometryValueError(
            f"Geometry source {obj.id} attribute {column!r} uses unit {unit!r}; "
            f"expected {expected_unit!r}"
        )

    raw_value = obj.attributes[column]
    if not raw_value.strip():
        raise GeometryValueError(
            f"Geometry source {obj.id} attribute {column!r} is required"
        )
    try:
        value = Decimal(raw_value.strip())
    except InvalidOperation as error:
        raise GeometryValueError(
            f"Geometry source {obj.id} attribute {column!r} is not a valid number: "
            f"{raw_value!r}"
        ) from error
    if not value.is_finite():
        raise GeometryValueError(
            f"Geometry source {obj.id} attribute {column!r} must be finite"
        )
    if value <= 0:
        raise GeometryValueError(
            f"Geometry source {obj.id} attribute {column!r} must be positive"
        )

    source = obj.attribute_sources.get(column)
    if source is None:
        raise GeometryValueError(
            f"Geometry source {obj.id} attribute {column!r} has no Markdown provenance"
        )
    return Quantity(value=value, unit=unit, source=source)


__all__ = [
    "GardenShedGeometrySpec",
    "GeometrySpec",
    "GeometryValueError",
    "Quantity",
    "parse_positive_quantity",
]
