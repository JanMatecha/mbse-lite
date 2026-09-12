from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..view_architecture import ViewDefinition


@dataclass(frozen=True, slots=True)
class GeneratedViews:
    """Views and text or binary assets contributed by one visualization generator."""

    views: tuple[ViewDefinition, ...] = ()
    assets: Mapping[str, str | bytes] = field(default_factory=dict)
