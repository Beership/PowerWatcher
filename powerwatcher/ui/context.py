"""Shared runtime context handed to every page."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..engine import Sampler
from ..storage import Store
from ..tariff import TariffEngine


@dataclass
class AppContext:
    store: Store
    settings: Settings
    engine: TariffEngine
    sampler: Sampler
