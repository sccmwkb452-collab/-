from __future__ import annotations

from typing import Any

from .base import SupplierAdapter
from .fragment import FragmentAdapter
from .manual import ManualAdapter, PolicyBlockedAdapter
from .reloadly import ReloadlyAdapter
from .smm_v2 import SmmV2Adapter

ADAPTERS: dict[str, type[SupplierAdapter]] = {
    cls.code: cls for cls in (SmmV2Adapter, ReloadlyAdapter, FragmentAdapter, ManualAdapter, PolicyBlockedAdapter)
}

# Tests replace adapters for a supplier code with fakes.
_overrides: dict[str, SupplierAdapter] = {}


def adapter_class(name: str) -> type[SupplierAdapter]:
    return ADAPTERS.get(name, ManualAdapter)


def build(supplier_code: str, adapter: str, credentials: dict[str, str], options: dict[str, Any]) -> SupplierAdapter:
    if supplier_code in _overrides:
        return _overrides[supplier_code]
    return adapter_class(adapter)(credentials, options)


def override(supplier_code: str, adapter: SupplierAdapter) -> None:
    _overrides[supplier_code] = adapter


def reset_overrides() -> None:
    _overrides.clear()
