"""District-level agronomic risk index — a lending input, not a credit score.

    python scripts/district_risk_index.py --year 2020
    python scripts/district_risk_index.py --year 2020 --out risk_index_2020.csv

Combines the district model's forecast for a season with each district's own historical
mean yield to produce a 0-100 risk index per district:

    shortfall   how far below the district's own historical average this season's
                forecast sits (the dominant signal — a bad season for a normally strong
                district)
    uncertainty how wide the model's 80% interval is relative to the forecast (a thin
                signal — few plots or a hard-to-predict district — is itself a risk,
                independent of the yield level)

    risk_index = 70 * shortfall_percentile + 30 * uncertainty_percentile   (0-100, per season)

Percentiles are computed within the scored season, so the index ranks districts against
each other in that season rather than against a fixed historical scale.

This is a DISTRICT-season aggregate. Documentation/kenya_maize_district_model_deployment.md
is explicit that the underlying model has no validated skill at the plot/farm level
(R2 ~ 0.18 ceiling there vs 0.22-0.59 at district level) — do not key loan decisions for an
individual borrower off their district's score alone. Use it to flag districts for
additional review or to price regional risk, not to approve or decline an individual
application.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd

from district_model import DistrictPipeline, TARGET, load_frame, load_schema, project_root

RISK_BANDS = [(66, "High"), (33, "Medium"), (0, "Low")]


def band(pct: float) -> str:
    for cutoff, label in RISK_BANDS:
        if pct >= cutoff:
            return label
    return "Low"


def build_risk_index(pipe: DistrictPipeline, frame: pd.DataFrame, history: pd.DataFrame,
                     min_plots: int | None = None) -> pd.DataFrame:
    table = pipe.predict_districts(frame, min_plots=min_plots)

    baseline = (history.groupby("district", observed=True)[TARGET]
                .mean().rename("baseline_mean"))
    table = table.merge(baseline, on="district", how="left")
    table["baseline_mean"] = table["baseline_mean"].fillna(table["pred_mean"])

    table["shortfall_pct"] = (table.baseline_mean - table.pred_mean) / table.baseline_mean
    table["interval_cv"] = (table.pred_hi - table.pred_lo) / table.pred_mean.clip(lower=1)

    table["shortfall_rank"] = table.shortfall_pct.rank(pct=True) * 100
    table["uncertainty_rank"] = table.interval_cv.rank(pct=True) * 100
    table["risk_index"] = (0.7 * table.shortfall_rank + 0.3 * table.uncertainty_rank).round(1)
    table["risk_band"] = table.risk_index.map(band)

    cols = ["district", "n_plots", "pred_mean", "baseline_mean", "shortfall_pct",
           "pred_lo", "pred_hi", "risk_index", "risk_band"]
    if "actual_mean" in table:
        cols.insert(5, "actual_mean")
    return table[cols].sort_values("risk_index", ascending=False).reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="data/models/district_v1", help="artefact directory")
    ap.add_argument("--year", type=int, required=True, help="season to score")
    ap.add_argument("--history-years", type=int, nargs="+",
                    help="years to average for each district's baseline "
                         "(default: every year before --year in the feature file)")
    ap.add_argument("--out", help="write the risk table here (CSV)")
    ap.add_argument("--min-plots", type=int, help="override the reporting threshold")
    ap.add_argument("--top", type=int, default=0, help="print only the top N districts by risk")
    args = ap.parse_args()

    root = project_root()
    model_dir = (root / args.model) if not Path(args.model).is_absolute() else Path(args.model)
    pipe = DistrictPipeline.load(model_dir)
    schema = load_schema(root)
    full = load_frame(root, schema)

    frame = full[full.year == args.year]
    if frame.empty:
        print(f"no rows for {args.year}")
        return 1

    hist_years = args.history_years or sorted(y for y in full.year.unique() if y < args.year)
    if not hist_years:
        print(f"no seasons before {args.year} to build a baseline from; "
              f"pass --history-years explicitly")
        return 1
    history = full[full.year.isin(hist_years)]

    table = build_risk_index(pipe, frame, history, min_plots=args.min_plots)

    trained = pipe.metadata_.get("train_years", [])
    print(f"district risk index for {args.year} — model trained on "
          f"{min(trained)}-{max(trained)}, baseline from {min(hist_years)}-{max(hist_years)} "
          f"({len(frame):,} plots, {len(table)} districts)\n")
    print("this is a district-season aggregate, not a per-borrower score — see module "
          "docstring and Documentation/kenya_maize_district_model_deployment.md\n")

    show = table.head(args.top) if args.top else table
    fmt = show.copy()
    for c in fmt.columns:
        if fmt[c].dtype.kind == "f" and c not in ("shortfall_pct", "risk_index"):
            fmt[c] = fmt[c].round(0).astype(int)
    fmt["shortfall_pct"] = (fmt["shortfall_pct"] * 100).round(1)
    print(fmt.to_string(index=False))

    if args.out:
        out_path = Path(args.out)
        table.to_csv(out_path, index=False)
        print(f"\nwritten to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
