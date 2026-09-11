from __future__ import annotations

import re
from html import escape

from ..core import Model, ModelObject
from ..view_architecture import ViewDefinition
from ._types import GeneratedViews


_PART_ROLES = {
    "enclosure": "Storage enclosure",
    "main_storage": "Main storage zone",
    "mower_compartment": "Enclosed mower compartment",
    "main_door": "Double-leaf main door",
    "mower_door": "Mower external door",
    "mower_ramp": "Mower access ramp",
    "shelving": "Right-end shelving unit",
}
_PREFERRED_CANDIDATE_NAMES = (
    "Mower door at end of long side",
    "Right-shifted main entrance after shelving",
)

_FOOTPRINT_PATTERN = re.compile(
    r"approximately\s+(\d+(?:\.\d+)?)\s*m\s*(?:×|x|by)\s*(\d+(?:\.\d+)?)\s*m",
    re.IGNORECASE,
)


def _part_roles(model: Model) -> dict[str, ModelObject] | None:
    parts_by_name = {
        obj.attributes.get("Name", "").strip().casefold(): obj
        for obj in model.objects.values()
        if obj.type == "Part"
    }
    roles: dict[str, ModelObject] = {}
    for role, name in _PART_ROLES.items():
        obj = parts_by_name.get(name.casefold())
        if obj is None:
            return None
        roles[role] = obj
    return roles


def _preferred_candidate_ids(model: Model) -> tuple[str, ...]:
    concepts_by_name = {
        obj.attributes.get("Name", "").strip().casefold(): obj
        for obj in model.objects.values()
        if obj.type == "Concept"
    }
    preferred_ids = []
    for name in _PREFERRED_CANDIDATE_NAMES:
        concept = concepts_by_name.get(name.casefold())
        if concept and concept.attributes.get("Status", "").strip().casefold() == "preferred candidate":
            preferred_ids.append(concept.id)
    return tuple(preferred_ids)


def _approximate_footprint(model: Model) -> tuple[float, float, str, str, str] | None:
    for obj in model.objects.values():
        if obj.type != "Requirement":
            continue
        text = " ".join(obj.attributes.values())
        match = _FOOTPRINT_PATTERN.search(text)
        if match is None:
            continue
        length, depth = (float(value) for value in match.groups())
        if length > 0 and depth > 0:
            return length, depth, obj.id, match.group(1), match.group(2)
    return None


def _svg_group(object_id: str, label: str, body: str) -> str:
    return (
        f'<g data-mbse-id="{escape(object_id, quote=True)}" '
        f'aria-label="{escape(object_id + " · " + label, quote=True)}">{body}</g>'
    )


def _floor_plan_svg(model: Model, roles: dict[str, ModelObject]) -> str:
    footprint = _approximate_footprint(model)
    if footprint is None:
        length, depth, footprint_id = 3.0, 1.0, None
        footprint_note = "Envelope aspect ratio uses a visualization-only 3:1 default."
    else:
        length, depth, footprint_id, length_text, depth_text = footprint
        footprint_note = (
            f"Envelope aspect ratio uses approximate project target {length_text} m × "
            f"{depth_text} m from {footprint_id}."
        )

    preferred_candidate_ids = _preferred_candidate_ids(model)
    if preferred_candidate_ids:
        candidate_note = (
            f"Preferred candidates shown: {', '.join(preferred_candidate_ids)}; positions are not "
            "accepted decisions."
        )
    else:
        candidate_note = "Door positions are neutral visualization-only placeholders."

    envelope_width = 840.0
    envelope_height = max(190.0, min(300.0, envelope_width * depth / length))
    x = 120.0
    y = 125.0
    mower_width = envelope_width * 0.22
    shelf_width = envelope_width * 0.11
    main_x = x + mower_width
    main_width = envelope_width - mower_width
    bottom = y + envelope_height

    main_door_left = x + envelope_width * 0.56
    main_door_width = envelope_width * 0.25
    main_door_mid = main_door_left + main_door_width / 2
    mower_door_left = x + mower_width * 0.18
    mower_door_width = mower_width * 0.58
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

    escaped_footprint_note = escape(footprint_note)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 570" role="img" aria-labelledby="floorplan-title floorplan-description">
  <title id="floorplan-title">Conceptual garden tool shed floor plan</title>
  <desc id="floorplan-description">{escaped_footprint_note} Internal sizes and positions are visualization-only placeholders. {escape(candidate_note)}</desc>
  <rect x="0" y="0" width="1080" height="570" fill="#ffffff"/>
  <text x="120" y="48" fill="#172033" font-size="30" font-weight="700">Conceptual floor plan</text>
  <text x="120" y="78" fill="#52606d" font-size="17">Not to scale where dimensions are TBD · click a modeled element to inspect it</text>
  {''.join(groups)}
  <g aria-label="Visualization basis">
    <rect x="120" y="503" width="840" height="54" rx="6" fill="#f6f7f9" stroke="#bcccdc"/>
    <text x="138" y="526" fill="#52606d" font-size="14">{escaped_footprint_note} Internal placements are visualization-only.</text>
    <text x="138" y="547" fill="#52606d" font-size="14">{escape(candidate_note)}</text>
  </g>
</svg>
'''


def generate_garden_shed_views(model: Model) -> GeneratedViews | None:
    """Generate the garden-shed conceptual floor plan when its modeled roles exist."""

    roles = _part_roles(model)
    if roles is None:
        return None
    preferred_candidate_ids = _preferred_candidate_ids(model)
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
                    "displayed_candidates": list(preferred_candidate_ids),
                },
            ),
        ),
        assets={"views/floorplan.svg": _floor_plan_svg(model, roles)},
    )
