"""Source-adapter package: one real adapter per supported discovery source."""

from __future__ import annotations

from .base import SourceAdapter
from .chevening import CheveningAdapter
from .daad import DaadAdapter
from .erasmus_mundus import ErasmusMundusAdapter
from .generic import build_configured_adapters
from .goi_ies import GoiIesAdapter
from .mastercard import MastercardAdapter
from .mext import MextAdapter
from .nl_scholarship import NlScholarshipAdapter
from .vlir_uos import VlirUosAdapter
from .wemakescholars import WeMakeScholarsAdapter


def build_adapters() -> list[SourceAdapter]:
    """Instantiate every known adapter (enabled and disabled)."""
    adapters: list[SourceAdapter] = [
        WeMakeScholarsAdapter(),
        ErasmusMundusAdapter(),
        DaadAdapter(),
        VlirUosAdapter(),
        CheveningAdapter(),
        GoiIesAdapter(),
        MextAdapter(),
        MastercardAdapter(),
        NlScholarshipAdapter(),
    ]
    adapters.extend(build_configured_adapters())
    return adapters


def adapter_by_id(source_id: str) -> SourceAdapter | None:
    wanted = (source_id or "").strip().lower()
    for adapter in build_adapters():
        if adapter.source_id == wanted:
            return adapter
    return None


__all__ = [
    "SourceAdapter",
    "build_adapters",
    "adapter_by_id",
    "CheveningAdapter",
    "DaadAdapter",
    "ErasmusMundusAdapter",
    "GoiIesAdapter",
    "MastercardAdapter",
    "MextAdapter",
    "NlScholarshipAdapter",
    "VlirUosAdapter",
    "WeMakeScholarsAdapter",
]
