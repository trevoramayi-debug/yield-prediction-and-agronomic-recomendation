"""Area-yield index insurance pricing — a premium-rate estimate, not a payout engine.

    python scripts/price_area_yield_insurance.py --year 2020
    python scripts/price_area_yield_insurance.py --year 2020 --trigger-pct 0.8 --loading-pct 0.25 \
        --out premiums_2020.csv

For each district this season, prices an area-yield insurance contract of the standard
design: it pays out whenever the district's *actual* average yield falls below a trigger
set as a percentage of the district's own historical average yield (the "Threshold Yield"):

    trigger_yield      = trigger_pct * baseline_mean   (the payout line, default 80% of normal)

    expected_shortfall = E[max(trigger_yield - Y, 0)],  Y ~ Normal(pred_mean, pred_sd)
                        = (trigger_yield - pred_mean) * Phi(z) + pred_sd * phi(z)
                          where z = (trigger_yield - pred_mean) / pred_sd

    pure_premium_pct   = expected_shortfall / trigger_yield * 100   (expected loss cost)
    premium_pct         = pure_premium_pct * (1 + loading_pct)       (rate actually charged)

pred_sd is not reconstructed from the (clipped) prediction interval — it is the same
sd(n) = sqrt(a + b/n) the pipeline already fits from validation-season residuals and returns
directly from predict_districts(), reused exactly.

WHAT THIS IS AND ISN'T
-----------------------
This prices and ranks districts for an insurance program AHEAD OF a season — a pricing and
reserving tool. It does not decide payouts. Whether any individual district's contract pays
out must be settled against a real, independently measured area yield (crop-cutting survey,
official agricultural statistics) at the end of the season — never against this model's own
forecast. Using the same model's prediction as both the price-setter and the payout trigger
would let the model's forecast error masquerade as insured risk, on top of the basis risk
(area yield vs. any one farmer's yield) the product already carries.

See Documentation/kenya_maize_district_model_deployment.md for the model's validated skill
(district-season R2 0.22-0.59; no validated skill at the plot/farm level, so this is priced
and settled at the district level only).

THE NORMAL APPROXIMATION
-------------------------
Treating district-mean yield as Normal(pred_mean, pred_sd) is a simplification made for a
first pricing pass. It has no floor at zero, so it mildly overstates expected_shortfall for
districts with a low predicted mean and a wide interval (thin plot counts). A program
pricing real premiums should sanity-check rates against a distribution that respects the
yield floor (e.g. lognormal) before finalizing them — this script is a starting estimate,
not the final rate.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
from scipy.stats import norm

from district_model import DistrictPipeline, TARGET, load_frame, load_schema, project_root

DEFAULT_TRIGGER_PCT = 0.80
DEFAULT_LOADING_PCT = 0.25


def price_area_yield_insurance(pipe: DistrictPipeline, frame: pd.DataFrame, history: pd.DataFrame,
                               trigger_pct: float = DEFAULT_TRIGGER_PCT,
                               loading_pct: float = DEFAULT_LOADING_PCT,
                               min_plots: int | None = None) -> pd.DataFrame:
    table = pipe.predict_districts(frame, min_plots=min_plots)

    baseline = (history.groupby("district", observed=True)[TARGET]
                .mean().rename("baseline_mean"))
    table = table.merge(baseline, on="district", how="left")
    table["baseline_mean"] = table["baseline_mean"].fillna(table["pred_mean"])

    table["trigger_yield"] = trigger_pct * table.baseline_mean

    z = (table.trigger_yield - table.pred_mean) / table.pred_sd
    table["payout_probability"] = norm.cdf(z)
    expected_shortfall = ((table.trigger_yield - table.pred_mean) * norm.cdf(z)
                          + table.pred_sd * norm.pdf(z))
    table["expected_shortfall"] = expected_shortfall.clip(lower=0.0)

    table["pure_premium_pct"] = table.expected_shortfall / table.trigger_yield * 100
    table["premium_pct"] = table.pure_premium_pct * (1 + loading_pct)

    cols = ["district", "n_plots", "pred_mean", "baseline_mean", "trigger_yield",
           "payout_probability", "expected_shortfall", "pure_premium_pct", "premium_pct"]
    if "actual_mean" in table:
        cols.insert(5, "actual_mean")
    return table[cols].sort_values("premium_pct", ascending=False).reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="data/models/district_v1", help="artefact directory")
    ap.add_argument("--year", type=int, required=True, help="season to price")
    ap.add_argument("--history-years", type=int, nargs="+",
                    help="years to average for each district's baseline / Threshold Yield "
                         "(default: every year before --year in the feature file)")
    ap.add_argument("--trigger-pct", type=float, default=DEFAULT_TRIGGER_PCT,
                    help=f"Threshold Yield as a fraction of the historical average "
                         f"(default {DEFAULT_TRIGGER_PCT})")
    ap.add_argument("--loading-pct", type=float, default=DEFAULT_LOADING_PCT,
                    help=f"margin added on top of the pure premium for admin, reinsurance "
                         f"and profit (default {DEFAULT_LOADING_PCT})")
    ap.add_argument("--out", help="write the premium table here (CSV)")
    ap.add_argument("--min-plots", type=int, help="override the reporting threshold")
    ap.add_argument("--top", type=int, default=0, help="print only the top N districts by premium")
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

    table = price_area_yield_insurance(pipe, frame, history, trigger_pct=args.trigger_pct,
                                       loading_pct=args.loading_pct, min_plots=args.min_plots)

    trained = pipe.metadata_.get("train_years", [])
    print(f"area-yield insurance pricing for {args.year} — model trained on "
          f"{min(trained)}-{max(trained)}, baseline from {min(hist_years)}-{max(hist_years)} "
          f"({len(frame):,} plots, {len(table)} districts)")
    print(f"trigger: {args.trigger_pct:.0%} of historical average yield  |  "
          f"loading: {args.loading_pct:.0%} on top of the pure premium\n")
    print("pricing/reserving estimate only — payout decisions must use a real, independently "
          "measured area yield at settlement, not this forecast. See module docstring and "
          "Documentation/kenya_maize_district_model_deployment.md\n")

    show = table.head(args.top) if args.top else table
    fmt = show.copy()
    for c in ("pred_mean", "baseline_mean", "trigger_yield", "expected_shortfall", "actual_mean"):
        if c in fmt.columns:
            fmt[c] = fmt[c].round(0).astype(int)
    fmt["payout_probability"] = (fmt["payout_probability"] * 100).round(1)
    fmt["pure_premium_pct"] = fmt["pure_premium_pct"].round(1)
    fmt["premium_pct"] = fmt["premium_pct"].round(1)
    print(fmt.to_string(index=False))

    if args.out:
        out_path = Path(args.out)
        table.to_csv(out_path, index=False)
        print(f"\nwritten to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
