from typing import Any

COORDINATE_KEYS = ("lat", "lon", "lng", "latitude", "longitude")


def strip_coordinates(data: dict[str, Any]) -> dict[str, Any]:
    """Defense in depth: drop coordinate-like keys. Schemas already reject them with 422."""
    return {k: v for k, v in data.items() if k.lower() not in COORDINATE_KEYS}
