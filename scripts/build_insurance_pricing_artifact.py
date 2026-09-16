"""Precompute district-season stats for area-yield insurance pricing.

    python scripts/build_insurance_pricing_artifact.py

Writes data/api/insurance_pricing.json: per-district (n_plots, pred_mean, pred_sd,
baseline_mean, actual_mean) for a single season, 2020.

WHY 2020 AND WHY district_v1, NOT THE LIVE district_v2 MODEL
---------------------------------------------------------------
Insurance pricing needs an honestly out-of-sample forecast -- a model that has not already
seen the outcome it is pricing. data/models/district_v1 was trained on 2016-2019 with 2020
held out as its test season (see Documentation/kenya_maize_district_model_deployment.md), so
its 2020 predictions are the one genuinely out-of-time district-season forecast this project
has. Every other year (2016-2019) was part of v1's training set, and district_v2 -- the
model api/registry.py actually serves live, trained on 2016-2020 -- saw 2020 too. Pricing off
either would be pricing off a forecast the model had already memorized the answer to.

This is therefore a fixed, single-season artefact rather than a live "forecast next season"
endpoint. Pricing a genuinely future season (2021+) is a different, harder problem -- it needs
a weather forecast or climatology-based approach, not this survey model -- and is out of scope
here; see scripts/price_area_yield_insurance.py's docstring for the same caveat.

CONSUMED BY
-----------
api/insurance.py reads this file and applies a caller-supplied trigger_pct / loading_pct at
request time (api/routers/insurance.py), rather than baking a fixed contract design into the
artefact -- those are business choices a program should be able to explore without a rebuild.
The pricing formula there mirrors scripts/price_area_yield_insurance.py exactly.

Rebuild after retraining district_v1: python scripts/build_insurance_pricing_artifact.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from district_model import DistrictPipeline, TARGET, load_frame, load_schema, project_root

MODEL_DIR = "data/models/district_v1"
YEAR = 2020
OUT_PATH_REL = "data/api/insurance_pricing.json"


def main() -> int:
    root = project_root()
    pipe = DistrictPipeline.load(root / MODEL_DIR)
    schema = load_schema(root)
    full = load_frame(root, schema)

    frame = full[full.year == YEAR]
    hist_years = sorted(int(y) for y in full.year.unique() if y < YEAR)
    history = full[full.year.isin(hist_years)]

    table = pipe.predict_districts(frame)
    baseline = (history.groupby("district", observed=True)[TARGET]
                .mean().rename("baseline_mean"))
    table = table.merge(baseline, on="district", how="left")
    table["baseline_mean"] = table["baseline_mean"].fillna(table["pred_mean"])

    has_actual = "actual_mean" in table.columns
    districts = [
        {
            "district": row.district,
            "n_plots": int(row.n_plots),
            "pred_mean": round(float(row.pred_mean), 2),
            "pred_sd": round(float(row.pred_sd), 2),
            "baseline_mean": round(float(row.baseline_mean), 2),
            "actual_mean": round(float(row.actual_mean), 2) if has_actual else None,
        }
        for row in table.itertuples()
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_dir": MODEL_DIR,
        "year": YEAR,
        "history_years": hist_years,
        "note": ("2020 is district_v1's held-out test season -- the only season this "
                "artefact prices, since it is the only one that model did not train on. "
                "The live API pipeline (district_v2) trained on 2016-2020 including this "
                "season, so it is deliberately not used here. See this script's docstring."),
        "districts": districts,
    }

    out_path = root / OUT_PATH_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {out_path.relative_to(root)} ({len(districts)} districts, year {YEAR})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
