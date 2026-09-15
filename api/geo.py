"""Access to the per-district geography in data/api/district_geo.json.

Built by `python scripts/build_district_geo.py` from the cleaned table's own
`field_latitude`/`field_longitude` and `yield_kg_ph` columns -- there is no
official district boundary file in this repo, so a district is a point (the
median GPS of its plots), not a polygon. The frontend turns those points into
map regions itself (a Voronoi tessellation clipped to the survey's own GPS
bounding box), which is why the point and the bbox travel together here.

Loaded once per process and treated as immutable, the same pattern as
api/curves.py and api/defaults.py.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from api.config import get_settings


class DistrictGeoUnavailable(RuntimeError):
    """The district geography artefact is missing or unreadable."""


class DistrictGeo:
    """Read-only view over data/api/district_geo.json."""

    def __init__(self, payload: dict) -> None:
        self._d = payload
        self.generated_at: str = payload.get("generated_at", "")
        self.source: dict = payload.get("source", {})
        self.unit: str = payload.get("unit", "kg/ha")
        self.bbox: dict = payload["bbox"]
        self.center: dict = payload["center"]
        self.performance_range: dict = payload["performance_range"]
        self.districts: list[dict] = payload["districts"]
        self._by_name = {d["district"]: d for d in self.districts}

    def get(self, district: str) -> dict | None:
        return self._by_name.get(str(district).strip().lower())


@lru_cache(maxsize=1)
def get_district_geo() -> DistrictGeo:
    path: Path = get_settings().district_geo_path
    if not path.exists():
        raise DistrictGeoUnavailable(
            f"district geography not found at {path}. "
            "Build it with: python scripts/build_district_geo.py")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DistrictGeoUnavailable(f"could not read district geography at {path}: {exc}") from exc
    return DistrictGeo(payload)


__all__ = ["DistrictGeo", "DistrictGeoUnavailable", "get_district_geo"]
