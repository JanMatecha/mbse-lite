from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from ..core import Model, ModelObject


PROFILE_COLUMN = "Visualization Profile"
ROLE_COLUMN = "Role"
OBJECT_ID_COLUMN = "Object ID"
EXPECTED_TYPE_COLUMN = "Expected Type"
PROFILE_COLUMNS = frozenset(
    {PROFILE_COLUMN, ROLE_COLUMN, OBJECT_ID_COLUMN, EXPECTED_TYPE_COLUMN}
)
_PROFILE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class VisualizationRoleMapping:
    """One non-authoritative semantic role mapped to an existing model object."""

    role: str
    object_id: str
    expected_type: str
    source_file: str


@dataclass(frozen=True, slots=True)
class VisualizationProfile:
    """Project-specific visualization roles, never engineering definitions."""

    name: str
    roles: Mapping[str, VisualizationRoleMapping]


def load_visualization_profiles(model: Model) -> dict[str, VisualizationProfile]:
    """Parse reserved visualization-profile Markdown tables from a loaded model.

    A table participates only when it contains the reserved ``Visualization
    Profile`` header. References and declared types are validated immediately so
    profile mistakes fail before any generated geometry is emitted.
    """

    mappings: dict[str, dict[str, VisualizationRoleMapping]] = {}
    for table_key, rows in sorted(model.tables.items()):
        if not rows:
            continue
        headers = set(rows[0])
        if PROFILE_COLUMN not in headers:
            continue
        missing_columns = PROFILE_COLUMNS - headers
        source_file = table_key.rsplit(":", 1)[0]
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(
                f"Visualization profile table in {source_file} is missing columns: {missing}"
            )

        for row_number, row in enumerate(rows, start=1):
            profile_name = row.get(PROFILE_COLUMN, "").strip()
            role = row.get(ROLE_COLUMN, "").strip()
            object_id = row.get(OBJECT_ID_COLUMN, "").strip()
            expected_type = row.get(EXPECTED_TYPE_COLUMN, "").strip()
            location = f"{source_file} row {row_number}"
            if not _PROFILE_NAME_PATTERN.fullmatch(profile_name):
                raise ValueError(
                    f"Invalid visualization profile name {profile_name!r} in {location}; "
                    "use lower-case letters, digits and underscores"
                )
            if not _PROFILE_NAME_PATTERN.fullmatch(role):
                raise ValueError(
                    f"Invalid visualization role {role!r} in {location}; "
                    "use lower-case letters, digits and underscores"
                )
            if not object_id:
                raise ValueError(
                    f"Visualization profile {profile_name!r} role {role!r} has no Object ID"
                )
            if not expected_type:
                raise ValueError(
                    f"Visualization profile {profile_name!r} role {role!r} has no Expected Type"
                )

            profile_roles = mappings.setdefault(profile_name, {})
            if role in profile_roles:
                raise ValueError(
                    f"Visualization profile {profile_name!r} defines role {role!r} more than once"
                )
            obj = model.objects.get(object_id)
            if obj is None:
                raise ValueError(
                    f"Visualization profile {profile_name!r} role {role!r} references "
                    f"missing object ID {object_id!r}"
                )
            if obj.type != expected_type:
                raise ValueError(
                    f"Visualization profile {profile_name!r} role {role!r} references "
                    f"{object_id!r} of type {obj.type!r}; expected {expected_type!r}"
                )
            profile_roles[role] = VisualizationRoleMapping(
                role=role,
                object_id=object_id,
                expected_type=expected_type,
                source_file=source_file,
            )

    return {
        name: VisualizationProfile(name=name, roles=dict(roles))
        for name, roles in mappings.items()
    }


def resolve_visualization_profile(
    model: Model,
    profile_name: str,
    required_roles: Mapping[str, str],
) -> dict[str, ModelObject] | None:
    """Resolve required semantic roles to model objects by stable MBSE ID.

    ``None`` means that the project did not opt into this profile. Once a
    profile is present, missing roles or incompatible declared types are errors.
    """

    profile = load_visualization_profiles(model).get(profile_name)
    if profile is None:
        return None

    missing_roles = sorted(set(required_roles) - set(profile.roles))
    if missing_roles:
        raise ValueError(
            f"Visualization profile {profile_name!r} is missing required roles: "
            f"{', '.join(missing_roles)}"
        )

    resolved: dict[str, ModelObject] = {}
    for role, required_type in required_roles.items():
        mapping = profile.roles[role]
        if mapping.expected_type != required_type:
            raise ValueError(
                f"Visualization profile {profile_name!r} role {role!r} declares type "
                f"{mapping.expected_type!r}; generator requires {required_type!r}"
            )
        resolved[role] = model.objects[mapping.object_id]
    return resolved


def validate_visualization_profiles(model: Model) -> list[tuple[str, str]]:
    """Return CLI-friendly errors for malformed or incompatible profiles."""

    try:
        load_visualization_profiles(model)
    except ValueError as error:
        return [("ERROR", str(error))]
    return []


__all__ = [
    "PROFILE_COLUMNS",
    "VisualizationProfile",
    "VisualizationRoleMapping",
    "load_visualization_profiles",
    "resolve_visualization_profile",
    "validate_visualization_profiles",
]
