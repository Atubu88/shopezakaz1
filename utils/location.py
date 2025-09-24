from __future__ import annotations

from typing import Any

import httpx


_USER_AGENT = "ShopezakazBot/1.0 (https://example.com)"


async def get_address_from_coords(lat: float, lon: float) -> str | None:
    """Получить человекопонятный адрес по координатам."""

    params = {
        "format": "jsonv2",
        "lat": f"{lat:.8f}",
        "lon": f"{lon:.8f}",
        "zoom": "18",
        "addressdetails": "1",
    }
    headers = {"User-Agent": _USER_AGENT}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
    except httpx.HTTPError:
        return None

    try:
        data: dict[str, Any] = response.json()
    except ValueError:
        return None
    display = data.get("display_name") or data.get("name")
    if isinstance(display, str) and display.strip():
        return display

    address = data.get("address")
    if isinstance(address, dict):
        parts = [str(value).strip() for value in address.values() if str(value).strip()]
        if parts:
            return ", ".join(parts)

    return None


def prettify_address(raw: str) -> str:
    """Сделать адрес компактным и пригодным для отображения."""

    normalized = " ".join(raw.replace("\n", " ").split())
    if not normalized:
        return ""

    parts = [part.strip() for part in normalized.split(",") if part.strip()]

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        lowered = part.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(part)

    if not deduped:
        deduped = [normalized.strip()]

    compact = ", ".join(deduped[:4])
    if len(compact) > 120:
        compact = compact[:117].rstrip(", ") + "..."

    return compact
