"""Area-yield insurance pricing -- a read-only view over the precomputed
district-season stats in data/api/insurance_pricing.json, plus the pricing
formula itself.

The precomputed stats (n_plots, pred_mean, pred_sd, baseline_mean, actual_mean)
are fixed once the artefact is built -- they come from the fitted model and the
historical survey, and rebuilding them needs the full plot-level frame this
service does not ship (see scripts/build_insurance_pricing_artifact.py).
trigger_pct and loading_pct are supplied by the caller and applied here at
request time instead, since they are contract-design choices a program should
be able to explore without a new build.

The formula mirrors scripts/price_area_yield_insurance.py exactly -- see that
script's docstring for the reasoning (Threshold Yield trigger, normal-
approximation expected shortfall, loading on top of the pure premium) and its
caveats: this prices and ranks districts ahead of a season, it does not decide
payouts, and the normal approximation has no floor at zero so it mildly
overstates the premium for low-mean, high-uncertainty districts.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from scipy.stats import norm

from api.config import get_settings


class InsurancePricingUnavailable(RuntimeError):
    """The precomputed district-season artefact is missing or unreadable."""


class InsurancePricing:
    """Read-only view over data/api/insurance_pricing.json."""

    def __init__(self, payload: dict) -> None:
        self._d = payload
        self.generated_at: str = payload.get("generated_at", "")
        self.model_dir: str = payload.get("model_dir", "")
        self.year: int = payload["year"]
        self.history_years: list[int] = payload.get("history_years", [])
        self.note: str = payload.get("note", "")
        self.districts: list[dict] = payload["districts"]

    def price(self, trigger_pct: float, loading_pct: float) -> list[dict]:
        """Apply a trigger and a loading to every precomputed district stat row."""
        rows = []
        for d in self.districts:
            trigger_yield = trigger_pct * d["baseline_mean"]
            sd = d["pred_sd"]
            z = (trigger_yield - d["pred_mean"]) / sd if sd > 0 else float("-inf")
            payout_probability = float(norm.cdf(z))
            expected_shortfall = max(
                0.0,
                (trigger_yield - d["pred_mean"]) * norm.cdf(z) + sd * norm.pdf(z),
            )
            pure_premium_pct = expected_shortfall / trigger_yield * 100 if trigger_yield else 0.0
            premium_pct = pure_premium_pct * (1 + loading_pct)
            rows.append({
                **d,
                "trigger_yield": round(trigger_yield, 2),
                "payout_probability": round(payout_probability, 4),
                "expected_shortfall": round(expected_shortfall, 2),
                "pure_premium_pct": round(pure_premium_pct, 2),
                "premium_pct": round(premium_pct, 2),
            })
        return sorted(rows, key=lambda r: r["premium_pct"], reverse=True)


@lru_cache(maxsize=1)
def get_insurance_pricing() -> InsurancePricing:
    path: Path = get_settings().insurance_pricing_path
    if not path.exists():
        raise InsurancePricingUnavailable(
            f"insurance pricing artefact not found at {path}. "
            "Build it with: python scripts/build_insurance_pricing_artifact.py")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InsurancePricingUnavailable(f"could not read {path}: {exc}") from exc
    return InsurancePricing(payload)
