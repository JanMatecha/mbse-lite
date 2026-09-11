from __future__ import annotations

from ..core import Model
from ._types import GeneratedViews
from .garden_shed import generate_garden_shed_views


def build_generated_views(model: Model) -> GeneratedViews:
    """Run the small registry of optional domain visualization generators."""

    views = []
    assets: dict[str, str] = {}
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


__all__ = ["GeneratedViews", "build_generated_views"]
