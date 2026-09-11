from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..view_architecture import ViewDefinition


@dataclass(frozen=True, slots=True)
class GeneratedViews:
    """Views and text assets contributed by one domain visualization generator."""

    views: tuple[ViewDefinition, ...] = ()
    assets: Mapping[str, str] = field(default_factory=dict)
