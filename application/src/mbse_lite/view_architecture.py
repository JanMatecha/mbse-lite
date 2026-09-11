from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

from .core import Model, Relation, validate_model


VIEW_SCHEMA_VERSION = "0.2"
MBSE_AREA = "MBSE"
PROJECT_MANAGEMENT_AREA = "Project Management"
PM_RELATION_AREA = "Project Management / Cross-area"

# The first five renderers use model.json directly. The remaining four are the
# public asset-view contract introduced by View Architecture V0.1.
SUPPORTED_VIEW_TYPES = frozenset(
    {
        "overview",
        "objects",
        "tables",
        "relations",
        "validation",
        "mermaid",
        "graph",
        "svg",
        "gltf",
    }
)
ASSET_SOURCE_REQUIRED_VIEW_TYPES = frozenset({"mermaid", "svg", "gltf"})


@dataclass(frozen=True, slots=True)
class ViewDefinition:
    """Navigation and renderer metadata for one generated viewer view."""

    id: str
    title: str
    group: str
    type: str
    source: str | None = None
    description: str = ""
    config: Mapping[str, object] = field(default_factory=dict)

    def to_manifest_entry(self) -> dict[str, object]:
        entry: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "group": self.group,
            "type": self.type,
        }
        if self.source:
            entry["source"] = self.source
        if self.description:
            entry["description"] = self.description
        if self.config:
            entry["config"] = dict(self.config)
        return entry


def area_for_source(source_file: str, object_type: str = "") -> str:
    normalized = source_file.replace("\\", "/")
    file_name = Path(normalized).name.lower()
    if normalized.startswith("project_management/") or "project_management" in file_name:
        return PROJECT_MANAGEMENT_AREA
    if object_type in {"Task", "Milestone"}:
        return PROJECT_MANAGEMENT_AREA
    return MBSE_AREA


def _mermaid_subset(model: Model, object_ids: set[str], relations: list[Relation]) -> str:
    lines = ["flowchart LR"]
    node_ids: dict[str, str] = {}
    for index, object_id in enumerate(sorted(object_ids)):
        obj = model.objects.get(object_id)
        if obj is None:
            continue
        label = obj.attributes.get("Name") or obj.attributes.get("Title") or obj.id
        safe_id = obj.id.replace("-", "_") if re.fullmatch(r"[A-Z]+-[0-9]{3}", obj.id) else f"node_{index}"
        node_ids[obj.id] = safe_id
        safe_label = escape(str(label), quote=True).replace("\n", " ")
        safe_object_id = escape(obj.id, quote=True)
        lines.append(f'    {safe_id}["{safe_object_id}<br/>{safe_label}"]')
    for rel in relations:
        if rel.source in node_ids and rel.target in node_ids:
            safe_relation = escape(rel.relation, quote=True).replace("|", "&#124;").replace("\n", " ")
            lines.append(
                f'    {node_ids[rel.source]} -->|{safe_relation}| {node_ids[rel.target]}'
            )
    return "\n".join(lines)


def build_viewer_model(model: Model) -> dict[str, object]:
    """Convert the internal model to the renderer-neutral generated model.json shape."""

    object_areas: dict[str, str] = {}
    objects: list[dict[str, object]] = []
    for obj in sorted(model.objects.values(), key=lambda item: item.id):
        area = area_for_source(obj.source_file, obj.type)
        object_areas[obj.id] = area
        objects.append(
            {
                "id": obj.id,
                "type": obj.type,
                "area": area,
                "name": obj.attributes.get("Name") or obj.attributes.get("Title") or obj.id,
                "status": obj.attributes.get("Status", ""),
                "source_file": obj.source_file,
                "attributes": obj.attributes,
            }
        )

    relations: list[dict[str, str]] = []
    for rel in model.relations:
        source_area = object_areas.get(rel.source, area_for_source(rel.source_file))
        target_area = object_areas.get(rel.target, source_area)
        area = (
            PM_RELATION_AREA
            if PROJECT_MANAGEMENT_AREA in {source_area, target_area}
            else MBSE_AREA
        )
        relations.append(
            {
                "source": rel.source,
                "relation": rel.relation,
                "target": rel.target,
                "source_file": rel.source_file,
                "area": area,
            }
        )

    findings = [
        {"severity": severity, "message": message}
        for severity, message in validate_model(model)
    ]

    supporting_tables: list[dict[str, object]] = []
    for key, rows in sorted(model.tables.items()):
        if not rows:
            continue
        headers = list(rows[0])
        header_set = set(headers)
        if "ID" in header_set or {"Source", "Relation", "Target"}.issubset(header_set):
            continue
        source_file = key.rsplit(":", 1)[0]
        supporting_tables.append(
            {
                "source_file": source_file,
                "area": area_for_source(source_file),
                "headers": headers,
                "rows": [[row.get(header, "") for header in headers] for row in rows],
            }
        )

    mbse_count = sum(area == MBSE_AREA for area in object_areas.values())
    project_management_count = sum(
        area == PROJECT_MANAGEMENT_AREA for area in object_areas.values()
    )
    return {
        "schema_version": VIEW_SCHEMA_VERSION,
        "objects": objects,
        "relations": relations,
        "tables": supporting_tables,
        "validation": findings,
        "summary": {
            "objects": len(objects),
            "mbse_objects": mbse_count,
            "project_management_objects": project_management_count,
            "relations": len(relations),
            "tables": len(supporting_tables),
            "validation_findings": len(findings),
        },
    }


def default_view_definitions() -> tuple[ViewDefinition, ...]:
    """Return the generic built-in navigation for any MBSE Lite project."""

    return (
        ViewDefinition(
            id="overview",
            title="Overview",
            group="System",
            type="overview",
            description="Summary of the engineering model and project execution data.",
        ),
        ViewDefinition(
            id="mbse",
            title="MBSE Objects",
            group="System",
            type="objects",
            description="Needs, requirements, functions, architecture, verification and engineering issues.",
            config={"area": MBSE_AREA, "search_id": "mbseSearch"},
        ),
        ViewDefinition(
            id="traceability",
            title="Traceability",
            group="System",
            type="mermaid",
            source="views/traceability.mmd",
            description="Engineering-object traceability generated from explicit relations.",
        ),
        ViewDefinition(
            id="project-data",
            title="Project Data",
            group="Data",
            type="tables",
            description="Supporting Markdown tables that are not objects or relations.",
        ),
        ViewDefinition(
            id="relations",
            title="Relations",
            group="Data",
            type="relations",
            description="All explicit relations, including cross-area links.",
        ),
        ViewDefinition(
            id="project-management",
            title="Project Management",
            group="Project",
            type="objects",
            description="Tasks, milestones and other execution-oriented objects.",
            config={"area": PROJECT_MANAGEMENT_AREA, "search_id": "pmSearch"},
        ),
        ViewDefinition(
            id="delivery-traceability",
            title="Delivery Traceability",
            group="Project",
            type="mermaid",
            source="views/delivery-traceability.mmd",
            description="Project-management and cross-area delivery links.",
        ),
        ViewDefinition(
            id="validation",
            title="Validation",
            group="Quality",
            type="validation",
            description="Structural and traceability findings from the Markdown model.",
        ),
    )


def is_safe_view_source(source: str) -> bool:
    """Return whether a view source is a safe bundle-relative POSIX path."""

    normalized = source.replace("\\", "/")
    relative = PurePosixPath(normalized)
    parts = normalized.split("/")
    return bool(
        normalized.strip()
        and "\x00" not in normalized
        and not relative.is_absolute()
        and all(part not in {"", ".", ".."} for part in parts)
        and ":" not in parts[0]
    )


def validate_view_definitions(
    views: Sequence[ViewDefinition],
    default_view: str | None,
) -> None:
    """Validate the intentionally small public View manifest contract."""

    seen_ids: set[str] = set()
    for view in views:
        if not view.id.strip():
            raise ValueError("View IDs must not be empty")
        if view.id in seen_ids:
            raise ValueError(f"Duplicate view ID: {view.id}")
        seen_ids.add(view.id)

        if view.source is not None and not is_safe_view_source(view.source):
            raise ValueError(f"View source must be a safe relative path: {view.source!r}")
        if view.type in ASSET_SOURCE_REQUIRED_VIEW_TYPES and not view.source:
            raise ValueError(f"View {view.id!r} of type {view.type!r} requires a source")

    if default_view is not None and default_view not in seen_ids:
        raise ValueError(f"Default view does not reference a defined view: {default_view!r}")


def build_viewer_manifest(
    project_name: str,
    views: Sequence[ViewDefinition] | None = None,
    *,
    default_view: str | None = None,
) -> dict[str, object]:
    definitions = tuple(views) if views is not None else default_view_definitions()
    selected_default = definitions[0].id if default_view is None and definitions else default_view
    validate_view_definitions(definitions, selected_default)
    return {
        "schema_version": VIEW_SCHEMA_VERSION,
        "project": project_name,
        "default_view": selected_default,
        "views": [view.to_manifest_entry() for view in definitions],
    }


def build_default_view_assets(model: Model) -> dict[str, str]:
    object_areas = {
        obj.id: area_for_source(obj.source_file, obj.type)
        for obj in model.objects.values()
    }
    mbse_ids = {
        object_id for object_id, area in object_areas.items() if area == MBSE_AREA
    }
    project_management_ids = {
        object_id
        for object_id, area in object_areas.items()
        if area == PROJECT_MANAGEMENT_AREA
    }
    mbse_relations = [
        rel for rel in model.relations if rel.source in mbse_ids and rel.target in mbse_ids
    ]
    delivery_relations = [
        rel
        for rel in model.relations
        if rel.source in project_management_ids or rel.target in project_management_ids
    ]
    delivery_ids = set(project_management_ids)
    for rel in delivery_relations:
        delivery_ids.update((rel.source, rel.target))

    return {
        "views/traceability.mmd": _mermaid_subset(model, mbse_ids, mbse_relations) + "\n",
        "views/delivery-traceability.mmd": _mermaid_subset(
            model, delivery_ids, delivery_relations
        )
        + "\n",
    }
