"""Low-cost property data engine.

This module keeps the default analysis path cheap: cached data, internal rent
estimates, Section 8/FMR-style estimates, and premium API placeholders only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional


PROPERTY_CACHE: dict[str, dict[str, Any]] = {}


def estimate_section8_rent(bedrooms: Optional[float], city: str = "", state: str = "") -> int:
    bedroom_count = int(bedrooms or 2)
    state_adjustments = {
        "IL": 0,
        "MI": -75,
        "OH": -100,
        "NY": 175,
        "PA": -50,
        "NJ": 250,
        "FL": 125,
        "TX": 50,
    }
    estimates = {
        0: 850,
        1: 950,
        2: 1250,
        3: 1550,
        4: 1850,
        5: 2100,
    }
    base = estimates.get(bedroom_count, 1200 + max(0, bedroom_count - 2) * 300)
    return max(650, base + state_adjustments.get((state or "").upper(), 0))


def estimate_rent(data: Mapping[str, Any]) -> int:
    bedrooms = int(float(data.get("bedrooms") or data.get("beds") or 2))
    sqft = float(data.get("sqft") or data.get("squareFootage") or 0)
    condition_score = float(data.get("conditionScore") or data.get("condition_score") or 60)

    if bedrooms <= 1:
        rent = 850
    elif bedrooms == 2:
        rent = 1100
    elif bedrooms == 3:
        rent = 1400
    else:
        rent = 1700

    if sqft > 1400:
        rent += 150
    if data.get("section8Area"):
        rent += 100
    if data.get("lowIncomeArea"):
        rent -= 50
    if condition_score > 75:
        rent += 200

    return max(600, rent)


def _cache_key(property_data: Mapping[str, Any]) -> str:
    return str(
        property_data.get("parcelId")
        or property_data.get("parcel_id")
        or property_data.get("address")
        or property_data.get("propertyAddress")
        or ""
    ).strip().lower()


def get_cached_property(cache_key: str) -> Optional[dict[str, Any]]:
    if not cache_key:
        return None
    cached = PROPERTY_CACHE.get(cache_key)
    if not cached:
        return None
    updated_at = cached.get("updatedAt")
    try:
        age_days = (datetime.utcnow() - datetime.fromisoformat(updated_at)).total_seconds() / 86400
    except Exception:
        return None
    return cached if age_days <= 30 else None


def enrich_property_low_cost(property_data: Mapping[str, Any]) -> dict[str, Any]:
    cache_key = _cache_key(property_data)
    cached = get_cached_property(cache_key)
    if cached:
        return {**cached, "cacheHit": True}

    city = str(property_data.get("city") or "")
    state = str(property_data.get("state") or "")
    bedrooms = property_data.get("bedrooms") or property_data.get("beds")
    rent_estimate = estimate_rent(property_data)
    section8_estimate = estimate_section8_rent(bedrooms, city, state)

    enriched = {
        **dict(property_data),
        "rentEstimate": rent_estimate,
        "section8Estimate": section8_estimate,
        "dataStrategy": "LOW_COST_ENGINE",
        "premiumApisUsed": False,
        "premiumApiPolicy": "RentCast and other paid APIs are disabled by default and reserved for future premium/high-score enrichment.",
        "enrichedAt": datetime.utcnow().isoformat(),
        "updatedAt": datetime.utcnow().isoformat(),
    }
    if cache_key:
        PROPERTY_CACHE[cache_key] = enriched
    return enriched


def calculate_low_cost_deal_score(property_data: Mapping[str, Any]) -> int:
    score = 20
    if property_data.get("taxDelinquent") or property_data.get("tax_delinquent"):
        score += 18
    if property_data.get("foreclosure"):
        score += 18
    if property_data.get("vacant"):
        score += 14
    if property_data.get("absenteeOwner") or property_data.get("absentee_owner"):
        score += 8
    if property_data.get("photos"):
        score += 5
    if property_data.get("sourceUrl") or property_data.get("source_url"):
        score += 5

    estimated_value = property_data.get("estimatedValue") or property_data.get("estimated_value")
    rent_estimate = property_data.get("rentEstimate") or property_data.get("estimatedRent")
    try:
        ratio = (float(rent_estimate) * 12) / float(estimated_value)
    except (TypeError, ValueError, ZeroDivisionError):
        ratio = 0
    if ratio >= 0.15:
        score += 25
    elif ratio >= 0.12:
        score += 18
    elif ratio >= 0.10:
        score += 12
    elif ratio and ratio < 0.08:
        score -= 8

    asking_price = property_data.get("askingPrice") or property_data.get("asking_price") or property_data.get("price")
    try:
        discount = (float(estimated_value) - float(asking_price)) / float(estimated_value)
    except (TypeError, ValueError, ZeroDivisionError):
        discount = 0
    if discount >= 0.25:
        score += 18
    elif discount >= 0.10:
        score += 10
    elif discount < -0.10:
        score -= 10

    return max(0, min(score, 100))


def analyze_low_cost_property(property_data: Mapping[str, Any]) -> dict[str, Any]:
    enriched = enrich_property_low_cost(property_data)
    deal_score = calculate_low_cost_deal_score(enriched)
    premium_data = None
    if deal_score >= 85:
        premium_data = {
            "future": "Premium enrichment placeholder. Paid APIs remain disabled until explicitly enabled for premium/high-score properties.",
        }
    return {
        "success": True,
        "strategy": "LOW_COST_ENGINE",
        "property": {
            **enriched,
            "dealScore": deal_score,
        },
        "premiumData": premium_data,
    }


def rent_comps(city: str, state: str, bedrooms: Optional[float]) -> dict[str, Any]:
    estimated = estimate_section8_rent(bedrooms, city, state)
    return {
        "success": True,
        "strategy": "LOW_COST_ENGINE",
        "comps": [
            {"address": f"Typical {city} {int(bedrooms or 2)}BR comp", "rent": estimated},
            {"address": f"Upper-band {city} {int(bedrooms or 2)}BR comp", "rent": estimated + 100},
            {"address": f"Conservative {city} {int(bedrooms or 2)}BR comp", "rent": max(600, estimated - 100)},
        ],
    }


def data_priority() -> dict[str, Any]:
    return {
        "success": True,
        "strategy": {
            "countyData": True,
            "internalRentEngine": True,
            "section8Estimates": True,
            "cacheEnabled": True,
            "premiumApisLimited": True,
            "rentcastDisabled": True,
            "priorityOrder": [
                "County Assessor",
                "County GIS",
                "Tax Delinquency",
                "Foreclosure Filings",
                "HUD/Section 8 Rent Data",
                "Internal Rent Engine",
                "Cached MLS/Public Data",
                "Optional Premium APIs",
            ],
        },
    }
