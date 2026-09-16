"""Extensible page catalog shared by the display and web control panel."""

from __future__ import annotations

from collections.abc import Iterable

PAGE_CATALOG = (
    {
        "id": "status",
        "title": "Status",
        "description": "CPU, temperatura, memória e uptime.",
        "kind": "native",
        "defaultEnabled": True,
        "defaultRefreshSeconds": 1,
        "minRefreshSeconds": 1,
    },
    {
        "id": "network",
        "title": "Rede",
        "description": "Hostname, Ethernet, Wi-Fi ativo e Tailscale.",
        "kind": "native",
        "defaultEnabled": True,
        "defaultRefreshSeconds": 5,
        "minRefreshSeconds": 2,
    },
    {
        "id": "hardware",
        "title": "Hardware",
        "description": "Modelo, kernel, USB e estado da interface SPI.",
        "kind": "native",
        "defaultEnabled": True,
        "defaultRefreshSeconds": 30,
        "minRefreshSeconds": 5,
    },
    {
        "id": "sysops",
        "title": "SysOps",
        "description": "Disco, gateway, alimentação e serviços locais.",
        "kind": "native",
        "defaultEnabled": False,
        "defaultRefreshSeconds": 15,
        "minRefreshSeconds": 5,
    },
    {
        "id": "weather",
        "title": "Clima",
        "description": "Condição atual, sensação, mínima, máxima e chuva.",
        "kind": "integration",
        "defaultEnabled": False,
        "defaultRefreshSeconds": 600,
        "minRefreshSeconds": 300,
    },
)

PAGE_BY_ID = {page["id"]: page for page in PAGE_CATALOG}
PAGE_IDS = tuple(PAGE_BY_ID)


def custom_metadata(definition: dict) -> dict:
    """Return catalog metadata for one validated custom page definition."""

    return {
        "id": definition["id"],
        "title": definition["title"],
        "description": definition.get("description") or "Fonte HTTP/JSON personalizada.",
        "kind": "custom",
        "defaultEnabled": True,
        "defaultRefreshSeconds": definition.get("refreshSeconds", 60),
        "minRefreshSeconds": 10,
        "removable": True,
    }


def catalog_for(custom_pages: Iterable[dict] | None = None) -> list[dict]:
    pages = [dict(page) for page in PAGE_CATALOG]
    pages.extend(custom_metadata(item) for item in (custom_pages or ()))
    return pages


def catalog_by_id(custom_pages: Iterable[dict] | None = None) -> dict[str, dict]:
    return {page["id"]: page for page in catalog_for(custom_pages)}


def public_catalog(custom_pages: Iterable[dict] | None = None):
    return catalog_for(custom_pages)
