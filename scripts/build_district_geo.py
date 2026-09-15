"""Build the district geography artefact the map view uses.

The frontend wants two things no other artefact carries: where each district
sits (so it can be placed on a map and zoomed to) and how it has performed
historically (so it can be shaded). Both are derivable from columns already in
the cleaned table -- `field_latitude`/`field_longitude` and `yield_kg_ph` --
so this script is standalone, like `build_api_defaults.py`: pandas and numpy
only, no model stack.

    python scripts/build_district_geo.py

Writes data/api/district_geo.json. Regenerate it whenever the cleaned table is
rebuilt (`clean_kenya_maize.py`).

The per-district point is the **median** of its plots' GPS, not the mean: a
median is unmoved by the odd mis-keyed coordinate that survives cleaning,
where a mean would drag the point toward it. `field_latitude`/`field_longitude`
are already screened to `KE_LAT_RANGE`/`KE_LON_RANGE` by
`clean_kenya_maize.validate_gps` (invalid pairs are nulled), so no re-filtering
is needed here -- this script just drops the (rare) rows still missing GPS
before taking the median.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

OUT_REL = Path("data") / "api" / "district_geo.json"

# Mirrors scripts/clean_kenya_maize.py -- the bounding box every field GPS pair
# was validated against. Shipped alongside the per-district points so the map
# can frame itself on Kenya without a boundary shapefile.
KE_LAT_RANGE = (-4.9, 5.1)
KE_LON_RANGE = (33.5, 42.0)


def project_root(start: Path | None = None) -> Path:
    p = (start or Path(__file__)).resolve()
    for cand in [p, *p.parents]:
        if (cand / "data" / "features").exists():
            return cand
    raise FileNotFoundError("could not locate the project root (data/features)")


def build(root: Path) -> dict:
    path = root / "data" / "cleaned" / "kenya_maize_cleaned.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run scripts/clean_kenya_maize.py first.")

    df = pd.read_csv(path, usecols=[
        "district", "year", "yield_kg_ph", "field_latitude", "field_longitude"])
    df["district"] = df["district"].astype(str).str.strip().str.lower()

    districts = []
    yields = []
    for district, g in df.groupby("district", sort=True):
        gps = g.dropna(subset=["field_latitude", "field_longitude"])
        yld = g["yield_kg_ph"].dropna()
        if gps.empty or yld.empty:
            continue                       # no district in this survey is this thin
        mean_yield = float(yld.mean())
        yields.append(mean_yield)
        districts.append({
            "district": district,
            "lat": round(float(gps["field_latitude"].median()), 5),
            "lon": round(float(gps["field_longitude"].median()), 5),
            "n_plots": int(len(g)),
            "n_plots_with_gps": int(len(gps)),
            "mean_yield_kg_ph": round(mean_yield, 1),
            "median_yield_kg_ph": round(float(yld.median()), 1),
            "years": sorted(int(y) for y in g["year"].dropna().unique()),
        })

    performance_range = {
        "min_mean_yield_kg_ph": round(min(yields), 1),
        "max_mean_yield_kg_ph": round(max(yields), 1),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"rows": int(len(df)), "districts": len(districts),
                   "file": "data/cleaned/kenya_maize_cleaned.csv"},
        "unit": "kg/ha",
        "bbox": {"lat": list(KE_LAT_RANGE), "lon": list(KE_LON_RANGE)},
        "center": {
            "lat": round(float(np.median([d["lat"] for d in districts])), 5),
            "lon": round(float(np.median([d["lon"] for d in districts])), 5),
        },
        "performance_range": performance_range,
        "districts": districts,
    }


def main() -> None:
    root = project_root()
    payload = build(root)
    out_path = root / OUT_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} ({len(payload['districts'])} districts)")


if __name__ == "__main__":
    main()
