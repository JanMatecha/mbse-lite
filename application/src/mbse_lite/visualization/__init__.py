from __future__ import annotations

from ..core import Model
from ._types import GeneratedViews
from .garden_shed import (
    GARDEN_SHED_PROFILE,
    GARDEN_SHED_REQUIRED_ROLES,
    generate_garden_shed_views,
)
from .profile import (
    load_visualization_profiles,
    resolve_visualization_profile,
    validate_visualization_profiles,
)


def build_generated_views(model: Model) -> GeneratedViews:
    """Run the small registry of optional domain visualization generators."""

    views = []
    assets: dict[str, str | bytes] = {}
    for generator in (generate_garden_shed_views,):
        generated = generator(model)
        if generated is None:
            continue
        views.extend(generated.views)
        for source, content in generated.assets.items():
            if source in assets:
                raise ValueError(f"Duplicate generated view asset: {source}")
            assets[source] = content
    return GeneratedViews(views=tuple(views), assets=assets)


def validate_visualizations(model: Model) -> list[tuple[str, str]]:
    """Validate profile references and generator-specific required roles."""

    findings = validate_visualization_profiles(model)
    if findings:
        return findings
    profiles = load_visualization_profiles(model)
    if GARDEN_SHED_PROFILE not in profiles:
        return []
    try:
        resolve_visualization_profile(
            model, GARDEN_SHED_PROFILE, GARDEN_SHED_REQUIRED_ROLES
        )
    except ValueError as error:
        return [("ERROR", str(error))]
    return []


__all__ = [
    "GeneratedViews",
    "build_generated_views",
    "load_visualization_profiles",
    "resolve_visualization_profile",
    "validate_visualizations",
]
