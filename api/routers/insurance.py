"""GET /api/v1/insurance/districts -- area-yield insurance premium estimates.

Internal / underwriting tool: prices each district's contract for the model's
held-out test season (2020) at a caller-chosen trigger and loading. Not linked
from the farmer-facing prediction flow -- see api/insurance.py for why the
season is fixed and scripts/price_area_yield_insurance.py for the formula and
its caveats.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from api.insurance import InsurancePricingUnavailable, get_insurance_pricing
from api.schemas import (DistrictPayout, DistrictPremium, ErrorResponse,
                         InsurancePayoutResponse, InsurancePricingResponse)

router = APIRouter(prefix="/api/v1/insurance", tags=["insurance"])

PRICING_NOTE = (
    "Pricing/reserving estimate only -- not a payout engine. Whether any district's "
    "contract actually pays out must be settled against a real, independently measured "
    "area yield at the end of the season, never against this forecast."
)


@router.get("/districts", response_model=InsurancePricingResponse,
            responses={503: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
            summary="Area-yield insurance premium estimate per district")
def districts(
    trigger_pct: float = Query(
        0.80, gt=0, le=1,
        description="Threshold Yield as a fraction of each district's historical average "
                    "yield -- the payout line. Typical range 0.6-0.9."),
    loading_pct: float = Query(
        0.25, ge=0,
        description="Margin added on top of the pure (expected-loss) premium for admin, "
                    "reinsurance and profit."),
) -> InsurancePricingResponse:
    try:
        pricing = get_insurance_pricing()
    except InsurancePricingUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    rows = pricing.price(trigger_pct=trigger_pct, loading_pct=loading_pct)

    return InsurancePricingResponse(
        year=pricing.year,
        model_dir=pricing.model_dir,
        trigger_pct=trigger_pct,
        loading_pct=loading_pct,
        generated_at=pricing.generated_at,
        note=f"{pricing.note} {PRICING_NOTE}",
        districts=[DistrictPremium(**row) for row in rows],
    )


@router.get("/payouts", response_model=InsurancePayoutResponse,
            responses={503: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
            summary="Area-yield insurance settlement (backtest) per district")
def payouts(
    trigger_pct: float = Query(
        0.65, gt=0, le=1,
        description="Threshold Yield as a fraction of each district's historical average "
                    "yield -- the payout line."),
    price_per_kg: float = Query(
        50.0, gt=0,
        description="Maize price used to convert the physical shortfall into a payout, "
                    "e.g. KES/kg. Not derived from any data this project ships."),
) -> InsurancePayoutResponse:
    try:
        pricing = get_insurance_pricing()
    except InsurancePricingUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    rows = pricing.settle(trigger_pct=trigger_pct, price_per_kg=price_per_kg)

    return InsurancePayoutResponse(
        year=pricing.year,
        trigger_pct=trigger_pct,
        price_per_kg=price_per_kg,
        generated_at=pricing.generated_at,
        note=pricing.note,
        districts=[DistrictPayout(**row) for row in rows],
    )
