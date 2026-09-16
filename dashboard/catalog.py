"""Canonical page catalog shared by the display and the web control panel."""

PAGE_CATALOG = (
    {
        "id": "status",
        "title": "Status",
        "description": "CPU, temperatura, memória e uptime.",
        "defaultEnabled": True,
        "defaultRefreshSeconds": 1,
        "minRefreshSeconds": 1,
    },
    {
        "id": "network",
        "title": "Rede",
        "description": "Hostname, Ethernet, Wi-Fi ativo e Tailscale.",
        "defaultEnabled": True,
        "defaultRefreshSeconds": 5,
        "minRefreshSeconds": 2,
    },
    {
        "id": "hardware",
        "title": "Hardware",
        "description": "Modelo, kernel, USB e estado da interface SPI.",
        "defaultEnabled": True,
        "defaultRefreshSeconds": 30,
        "minRefreshSeconds": 5,
    },
)

PAGE_BY_ID = {page["id"]: page for page in PAGE_CATALOG}
PAGE_IDS = tuple(PAGE_BY_ID)


def public_catalog():
    return [dict(page) for page in PAGE_CATALOG]
