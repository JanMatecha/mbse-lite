from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from html import escape
from typing import Mapping

from ..core import Model, ModelObject
from ..geometry import GardenShedGeometrySpec, parse_positive_quantity
from ..view_architecture import ViewDefinition
from ._types import GeneratedViews
from .profile import resolve_visualization_profile


GARDEN_SHED_PROFILE = "garden_shed"
GARDEN_SHED_REQUIRED_ROLES = {
    "enclosure": "Part",
    "main_storage": "Part",
    "mower_compartment": "Part",
    "main_door": "Part",
    "mower_door": "Part",
    "mower_ramp": "Part",
    "shelving": "Part",
    "footprint": "Requirement",
    "mower_door_candidate": "Concept",
    "main_door_candidate": "Concept",
}

GARDEN_SHED_CANDIDATE_ROLES = (
    "mower_door_candidate",
    "main_door_candidate",
)


@dataclass(frozen=True, slots=True)
class GardenShedVisualizationSpec:
    """Shared engineering inputs and presentation defaults for SVG and GLB."""

    roles: Mapping[str, ModelObject]
    geometry: GardenShedGeometrySpec
    footprint_note: str
    displayed_candidate_ids: tuple[str, ...]
    candidate_note: str
    mower_fraction: float = 0.22
    shelving_fraction: float = 0.11
    main_door_start: float = 0.56
    main_door_fraction: float = 0.25
    mower_door_start: float = 0.18
    mower_door_fraction: float = 0.58
    conceptual_height: float = 2.2
    wall_thickness: float = 0.06
    floor_thickness: float = 0.08
    door_height: float = 1.85
    shelving_height: float = 1.55
    ramp_length: float = 0.8

    @property
    def length(self) -> float:
        return float(self.geometry.external_length.value)

    @property
    def depth(self) -> float:
        return float(self.geometry.external_depth.value)


@dataclass(frozen=True, slots=True)
class _Box:
    name: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    material: str
    rotation: tuple[float, float, float, float] | None = None


def build_garden_shed_geometry_spec(
    roles: Mapping[str, ModelObject],
) -> GardenShedGeometrySpec:
    """Resolve authoritative footprint inputs from the explicitly mapped source."""

    source = roles["footprint"]
    return GardenShedGeometrySpec(
        source_object_id=source.id,
        external_length=parse_positive_quantity(
            source,
            "Target Length",
            expected_unit="m",
            expected_object_type="Requirement",
        ),
        external_depth=parse_positive_quantity(
            source,
            "Target Depth",
            expected_unit="m",
            expected_object_type="Requirement",
        ),
    )


def _visualization_spec(roles: Mapping[str, ModelObject]) -> GardenShedVisualizationSpec:
    geometry = build_garden_shed_geometry_spec(roles)
    length = geometry.external_length
    depth = geometry.external_depth
    footprint_note = (
        f"Envelope aspect ratio uses approximate project target {length.value} {length.unit} × "
        f"{depth.value} {depth.unit} from {geometry.source_object_id}."
    )

    displayed_candidate_ids = tuple(
        roles[role].id for role in GARDEN_SHED_CANDIDATE_ROLES
    )
    if displayed_candidate_ids:
        candidate_note = (
            "Geometry candidates mapped by the visualization profile: "
            f"{', '.join(displayed_candidate_ids)}; positions are not accepted decisions."
        )
    else:
        candidate_note = "Door positions are neutral visualization-only placeholders."

    return GardenShedVisualizationSpec(
        roles=roles,
        geometry=geometry,
        footprint_note=footprint_note,
        displayed_candidate_ids=displayed_candidate_ids,
        candidate_note=candidate_note,
    )


def _svg_group(object_id: str, label: str, body: str) -> str:
    return (
        f'<g data-mbse-id="{escape(object_id, quote=True)}" '
        f'aria-label="{escape(object_id + " · " + label, quote=True)}">{body}</g>'
    )


def _floor_plan_svg(spec: GardenShedVisualizationSpec) -> str:
    roles = spec.roles
    envelope_width = 840.0
    envelope_height = max(
        190.0, min(300.0, envelope_width * spec.depth / spec.length)
    )
    x = 120.0
    y = 125.0
    mower_width = envelope_width * spec.mower_fraction
    shelf_width = envelope_width * spec.shelving_fraction
    main_x = x + mower_width
    main_width = envelope_width - mower_width
    bottom = y + envelope_height

    main_door_left = x + envelope_width * spec.main_door_start
    main_door_width = envelope_width * spec.main_door_fraction
    main_door_mid = main_door_left + main_door_width / 2
    mower_door_left = x + mower_width * spec.mower_door_start
    mower_door_width = mower_width * spec.mower_door_fraction
    ramp_top_y = bottom + 5
    ramp_bottom_y = bottom + 92

    label = lambda role: roles[role].attributes.get("Name", roles[role].id)
    groups = [
        _svg_group(
            roles["main_storage"].id,
            label("main_storage"),
            f'<rect x="{main_x:.1f}" y="{y + 10:.1f}" width="{main_width - 10:.1f}" '
            f'height="{envelope_height - 20:.1f}" rx="8" fill="#eaf2ff" stroke="#7aa2d8" stroke-width="2"/>'
            f'<text x="{main_x + 24:.1f}" y="{y + 48:.1f}" fill="#27466f" font-size="22">Main storage zone</text>',
        ),
        _svg_group(
            roles["mower_compartment"].id,
            label("mower_compartment"),
            f'<rect x="{x + 10:.1f}" y="{y + 10:.1f}" width="{mower_width - 20:.1f}" '
            f'height="{envelope_height - 20:.1f}" rx="8" fill="#edf7e8" stroke="#70a65c" stroke-width="2"/>'
            f'<text x="{x + mower_width / 2:.1f}" y="{y + 55:.1f}" text-anchor="middle" fill="#355e2b" font-size="18">Mower</text>'
            f'<text x="{x + mower_width / 2:.1f}" y="{y + 79:.1f}" text-anchor="middle" fill="#355e2b" font-size="18">compartment</text>',
        ),
        _svg_group(
            roles["shelving"].id,
            label("shelving"),
            f'<rect x="{x + envelope_width - shelf_width:.1f}" y="{y + 18:.1f}" width="{shelf_width - 10:.1f}" '
            f'height="{envelope_height - 36:.1f}" fill="#fff0cc" stroke="#b77a19" stroke-width="3" stroke-dasharray="7 5"/>'
            f'<line x1="{x + envelope_width - shelf_width + 8:.1f}" y1="{y + envelope_height * .44:.1f}" '
            f'x2="{x + envelope_width - 10:.1f}" y2="{y + envelope_height * .44:.1f}" stroke="#b77a19" stroke-width="2"/>'
            f'<line x1="{x + envelope_width - shelf_width + 8:.1f}" y1="{y + envelope_height * .68:.1f}" '
            f'x2="{x + envelope_width - 10:.1f}" y2="{y + envelope_height * .68:.1f}" stroke="#b77a19" stroke-width="2"/>'
            f'<text x="{x + envelope_width - shelf_width / 2 - 5:.1f}" y="{y + envelope_height / 2:.1f}" '
            f'text-anchor="middle" fill="#80520e" font-size="15" transform="rotate(-90 {x + envelope_width - shelf_width / 2 - 5:.1f} {y + envelope_height / 2:.1f})">Right-end shelving</text>',
        ),
        _svg_group(
            roles["main_door"].id,
            label("main_door"),
            f'<line x1="{main_door_left:.1f}" y1="{bottom:.1f}" x2="{main_door_mid:.1f}" y2="{bottom + 74:.1f}" stroke="#805ad5" stroke-width="7"/>'
            f'<line x1="{main_door_left + main_door_width:.1f}" y1="{bottom:.1f}" x2="{main_door_mid:.1f}" y2="{bottom + 74:.1f}" stroke="#805ad5" stroke-width="7"/>'
            f'<text x="{main_door_mid:.1f}" y="{bottom + 100:.1f}" text-anchor="middle" fill="#5a3b98" font-size="17">Double-leaf main door</text>',
        ),
        _svg_group(
            roles["mower_door"].id,
            label("mower_door"),
            f'<line x1="{mower_door_left:.1f}" y1="{bottom:.1f}" x2="{mower_door_left + mower_door_width:.1f}" y2="{bottom:.1f}" stroke="#157f8c" stroke-width="9"/>'
            f'<text x="{mower_door_left + mower_door_width / 2:.1f}" y="{bottom + 28:.1f}" text-anchor="middle" fill="#12626b" font-size="15">Mower access</text>',
        ),
        _svg_group(
            roles["mower_ramp"].id,
            label("mower_ramp"),
            f'<path d="M {mower_door_left:.1f} {ramp_top_y:.1f} L {mower_door_left - 20:.1f} {ramp_bottom_y:.1f} '
            f'L {mower_door_left + mower_door_width + 20:.1f} {ramp_bottom_y:.1f} L {mower_door_left + mower_door_width:.1f} {ramp_top_y:.1f} Z" '
            f'fill="#d9f3f5" stroke="#157f8c" stroke-width="3" stroke-dasharray="8 5"/>'
            f'<text x="{mower_door_left + mower_door_width / 2:.1f}" y="{ramp_bottom_y - 18:.1f}" text-anchor="middle" fill="#12626b" font-size="15">Conceptual ramp</text>',
        ),
        _svg_group(
            roles["enclosure"].id,
            label("enclosure"),
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{envelope_width:.1f}" height="{envelope_height:.1f}" '
            f'rx="4" fill="none" stroke="#243b53" stroke-width="9"/>'
            f'<text x="{x:.1f}" y="{y - 20:.1f}" fill="#243b53" font-size="23">Storage enclosure</text>',
        ),
    ]

    escaped_footprint_note = escape(spec.footprint_note)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 570" role="img" aria-labelledby="floorplan-title floorplan-description">
  <title id="floorplan-title">Conceptual garden tool shed floor plan</title>
  <desc id="floorplan-description">{escaped_footprint_note} Internal sizes and positions are visualization-only placeholders. {escape(spec.candidate_note)}</desc>
  <rect x="0" y="0" width="1080" height="570" fill="#ffffff"/>
  <text x="120" y="48" fill="#172033" font-size="30" font-weight="700">Conceptual floor plan</text>
  <text x="120" y="78" fill="#52606d" font-size="17">Not to scale where dimensions are TBD · click a modeled element to inspect it</text>
  {''.join(groups)}
  <g aria-label="Visualization basis">
    <rect x="120" y="503" width="840" height="54" rx="6" fill="#f6f7f9" stroke="#bcccdc"/>
    <text x="138" y="526" fill="#52606d" font-size="14">{escaped_footprint_note} Internal placements are visualization-only.</text>
    <text x="138" y="547" fill="#52606d" font-size="14">{escape(spec.candidate_note)}</text>
  </g>
</svg>
'''


_MATERIAL_COLORS: tuple[tuple[str, tuple[float, float, float, float]], ...] = (
    ("enclosure", (0.18, 0.27, 0.36, 0.30)),
    ("main_storage", (0.40, 0.63, 0.88, 0.48)),
    ("mower_compartment", (0.43, 0.67, 0.34, 0.52)),
    ("main_door", (0.50, 0.35, 0.78, 1.0)),
    ("mower_access", (0.08, 0.50, 0.55, 1.0)),
    ("ramp", (0.35, 0.72, 0.75, 0.85)),
    ("shelving", (0.82, 0.55, 0.15, 0.72)),
)


def _box_groups(
    spec: GardenShedVisualizationSpec,
) -> tuple[tuple[str, tuple[_Box, ...]], ...]:
    length = spec.length
    depth = spec.depth
    height = spec.conceptual_height
    wall = spec.wall_thickness
    floor = spec.floor_thickness
    left = -length / 2
    right = length / 2
    front = depth / 2
    rear = -depth / 2
    mower_length = length * spec.mower_fraction
    split = left + mower_length
    main_length = length - mower_length
    zone_depth = max(depth - 2 * wall, depth * 0.8)

    main_door_left = left + length * spec.main_door_start
    main_door_width = length * spec.main_door_fraction
    main_leaf_width = max(main_door_width / 2 - 0.015, 0.05)
    mower_door_left = left + mower_length * spec.mower_door_start
    mower_door_width = mower_length * spec.mower_door_fraction
    door_z = front + wall * 0.55
    door_y = floor + spec.door_height / 2

    ramp_rise = floor * 2
    ramp_angle = math.atan2(ramp_rise, spec.ramp_length)
    ramp_rotation = (math.sin(ramp_angle / 2), 0.0, 0.0, math.cos(ramp_angle / 2))

    return (
        (
            "enclosure",
            (
                _Box(
                    "Rear conceptual wall",
                    (0.0, height / 2, rear),
                    (length, height, wall),
                    "enclosure",
                ),
                _Box(
                    "Left conceptual wall",
                    (left, height / 2, 0.0),
                    (wall, height, depth),
                    "enclosure",
                ),
                _Box(
                    "Right conceptual wall",
                    (right, height / 2, 0.0),
                    (wall, height, depth),
                    "enclosure",
                ),
                _Box(
                    "Front conceptual sill",
                    (0.0, floor, front),
                    (length, floor * 2, wall),
                    "enclosure",
                ),
            ),
        ),
        (
            "main_storage",
            (
                _Box(
                    "Main storage visualization volume",
                    (split + main_length / 2, floor / 2, 0.0),
                    (max(main_length - 2 * wall, wall), floor, zone_depth),
                    "main_storage",
                ),
            ),
        ),
        (
            "mower_compartment",
            (
                _Box(
                    "Mower compartment visualization volume",
                    (left + mower_length / 2, floor / 2, 0.0),
                    (max(mower_length - 2 * wall, wall), floor, zone_depth),
                    "mower_compartment",
                ),
                _Box(
                    "Conceptual compartment divider",
                    (split, height * 0.45, 0.0),
                    (wall, height * 0.9, depth),
                    "mower_compartment",
                ),
            ),
        ),
        (
            "main_door",
            (
                _Box(
                    "Main door left leaf",
                    (main_door_left + main_leaf_width / 2, door_y, door_z),
                    (main_leaf_width, spec.door_height, wall),
                    "main_door",
                ),
                _Box(
                    "Main door right leaf",
                    (
                        main_door_left + main_door_width - main_leaf_width / 2,
                        door_y,
                        door_z,
                    ),
                    (main_leaf_width, spec.door_height, wall),
                    "main_door",
                ),
            ),
        ),
        (
            "mower_door",
            (
                _Box(
                    "Mower external access",
                    (mower_door_left + mower_door_width / 2, door_y, door_z),
                    (mower_door_width, spec.door_height, wall),
                    "mower_access",
                ),
            ),
        ),
        (
            "mower_ramp",
            (
                _Box(
                    "Conceptual mower ramp",
                    (
                        mower_door_left + mower_door_width / 2,
                        ramp_rise / 2,
                        front + spec.ramp_length / 2,
                    ),
                    (mower_door_width * 1.08, floor * 0.55, spec.ramp_length),
                    "ramp",
                    ramp_rotation,
                ),
            ),
        ),
        (
            "shelving",
            (
                _Box(
                    "Right-end shelving visualization volume",
                    (
                        right - length * spec.shelving_fraction / 2,
                        floor + spec.shelving_height / 2,
                        0.0,
                    ),
                    (
                        length * spec.shelving_fraction,
                        spec.shelving_height,
                        depth * 0.72,
                    ),
                    "shelving",
                ),
            ),
        ),
    )


def _cube_buffer() -> tuple[bytes, int, int, int]:
    faces = (
        ((1.0, 0.0, 0.0), ((0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5), (0.5, -0.5, 0.5))),
        ((-1.0, 0.0, 0.0), ((-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (-0.5, 0.5, -0.5), (-0.5, -0.5, -0.5))),
        ((0.0, 1.0, 0.0), ((-0.5, 0.5, -0.5), (-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5))),
        ((0.0, -1.0, 0.0), ((-0.5, -0.5, 0.5), (-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5))),
        ((0.0, 0.0, 1.0), ((-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5))),
        ((0.0, 0.0, -1.0), ((0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5))),
    )
    positions: list[float] = []
    normals: list[float] = []
    indices: list[int] = []
    for face_index, (normal, vertices) in enumerate(faces):
        for vertex in vertices:
            positions.extend(vertex)
            normals.extend(normal)
        offset = face_index * 4
        indices.extend((offset, offset + 1, offset + 2, offset, offset + 2, offset + 3))

    position_bytes = struct.pack(f"<{len(positions)}f", *positions)
    normal_bytes = struct.pack(f"<{len(normals)}f", *normals)
    index_bytes = struct.pack(f"<{len(indices)}H", *indices)
    normal_offset = len(position_bytes)
    index_offset = normal_offset + len(normal_bytes)
    return position_bytes + normal_bytes + index_bytes, normal_offset, index_offset, len(indices)


def _gltf_material(name: str, color: tuple[float, float, float, float]) -> dict[str, object]:
    material: dict[str, object] = {
        "name": name.replace("_", " ").title(),
        "pbrMetallicRoughness": {
            "baseColorFactor": list(color),
            "metallicFactor": 0.0,
            "roughnessFactor": 0.82,
        },
        "doubleSided": True,
    }
    if color[3] < 1.0:
        material["alphaMode"] = "BLEND"
    return material


def _conceptual_glb(spec: GardenShedVisualizationSpec) -> bytes:
    binary, normal_offset, index_offset, index_count = _cube_buffer()
    materials = [_gltf_material(name, color) for name, color in _MATERIAL_COLORS]
    material_indexes = {name: index for index, (name, _) in enumerate(_MATERIAL_COLORS)}
    meshes = [
        {
            "name": material["name"],
            "primitives": [
                {
                    "attributes": {"POSITION": 0, "NORMAL": 1},
                    "indices": 2,
                    "material": index,
                }
            ],
        }
        for index, material in enumerate(materials)
    ]

    nodes: list[dict[str, object]] = []
    scene_nodes: list[int] = []
    for role, boxes in _box_groups(spec):
        model_object = spec.roles[role]
        group_index = len(nodes)
        group: dict[str, object] = {
            "name": model_object.attributes.get("Name", model_object.id),
            "extras": {"mbse_id": model_object.id},
            "children": [],
        }
        nodes.append(group)
        scene_nodes.append(group_index)
        children = group["children"]
        assert isinstance(children, list)
        for box in boxes:
            child: dict[str, object] = {
                "name": box.name,
                "mesh": material_indexes[box.material],
                "translation": list(box.center),
                "scale": list(box.size),
            }
            if box.rotation is not None:
                child["rotation"] = list(box.rotation)
            children.append(len(nodes))
            nodes.append(child)

    document = {
        "asset": {
            "version": "2.0",
            "generator": "MBSE Lite conceptual GLB generator",
            "extras": {
                "geometry_status": "conceptual",
                "not_cad_authoritative": True,
            },
        },
        "scene": 0,
        "scenes": [{"name": "Conceptual 3D view", "nodes": scene_nodes}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": normal_offset, "target": 34962},
            {
                "buffer": 0,
                "byteOffset": normal_offset,
                "byteLength": index_offset - normal_offset,
                "target": 34962,
            },
            {
                "buffer": 0,
                "byteOffset": index_offset,
                "byteLength": len(binary) - index_offset,
                "target": 34963,
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 24,
                "type": "VEC3",
                "min": [-0.5, -0.5, -0.5],
                "max": [0.5, 0.5, 0.5],
            },
            {"bufferView": 1, "componentType": 5126, "count": 24, "type": "VEC3"},
            {
                "bufferView": 2,
                "componentType": 5123,
                "count": index_count,
                "type": "SCALAR",
                "min": [0],
                "max": [23],
            },
        ],
    }

    json_bytes = json.dumps(
        document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    json_bytes += b" " * (-len(json_bytes) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    total_length = 12 + 8 + len(json_bytes) + 8 + len(binary)
    return b"".join(
        (
            struct.pack("<4sII", b"glTF", 2, total_length),
            struct.pack("<I4s", len(json_bytes), b"JSON"),
            json_bytes,
            struct.pack("<I4s", len(binary), b"BIN\x00"),
            binary,
        )
    )


def generate_garden_shed_views(model: Model) -> GeneratedViews | None:
    """Generate garden-shed conceptual views when all modeled roles exist."""

    roles = resolve_visualization_profile(
        model, GARDEN_SHED_PROFILE, GARDEN_SHED_REQUIRED_ROLES
    )
    if roles is None:
        return None
    spec = _visualization_spec(roles)
    visualization_defaults = {
        "height_m": spec.conceptual_height,
        "wall_thickness_m": spec.wall_thickness,
        "floor_thickness_m": spec.floor_thickness,
        "door_height_m": spec.door_height,
        "ramp_length_m": spec.ramp_length,
        "mower_zone_fraction": spec.mower_fraction,
        "shelving_length_fraction": spec.shelving_fraction,
    }
    return GeneratedViews(
        views=(
            ViewDefinition(
                id="floor-plan",
                title="Floor Plan",
                group="Geometry",
                type="svg",
                source="views/floorplan.svg",
                description=(
                    "Conceptual 2D layout derived from modeled parts. Approximate envelope data may set "
                    "the aspect ratio; unresolved internal geometry remains visualization-only."
                ),
                config={
                    "geometry_status": "conceptual",
                    "not_to_scale_where_tbd": True,
                    "displayed_candidates": list(spec.displayed_candidate_ids),
                },
            ),
            ViewDefinition(
                id="conceptual-3d",
                title="3D",
                group="Geometry",
                type="gltf",
                source="views/model.glb",
                description=(
                    "Conceptual 3D view. Simple generated volumes share stable MBSE identities; "
                    "unresolved geometry uses visualization-only defaults and is not construction-ready."
                ),
                config={
                    "geometry_status": "conceptual",
                    "not_construction_ready": True,
                    "displayed_candidates": list(spec.displayed_candidate_ids),
                    "visualization_defaults": visualization_defaults,
                },
            ),
        ),
        assets={
            "views/floorplan.svg": _floor_plan_svg(spec),
            "views/model.glb": _conceptual_glb(spec),
        },
    )
