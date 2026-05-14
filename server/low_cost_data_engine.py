"""Realtime data policy helpers.

This module keeps cache and deal-score utilities, but it does not fabricate
live rent comps, Section 8 values, or premium provider payloads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional


PROPERTY_CACHE: dict[str, dict[str, Any]] = {}


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

    enriched = {
        **dict(property_data),
        "dataStrategy": "REALTIME_ONLY",
        "premiumApisUsed": False,
        "premiumApiPolicy": "Paid APIs are used only when explicitly configured. Missing provider data is reported as unavailable.",
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
    return {
        "success": True,
        "strategy": "REALTIME_ONLY",
        "property": {
            **enriched,
            "dealScore": deal_score,
        },
        "premiumData": None,
        "message": "No synthetic enrichment was applied. Connect live providers or import source data for additional fields.",
    }


def rent_comps(city: str, state: str, bedrooms: Optional[float]) -> dict[str, Any]:
    from sqlalchemy import select

    from server.property_system import _jsonable, _row_to_dict, get_property_engine
    from server.rent_analyzer import rental_comps

    statement = select(rental_comps).where(rental_comps.c.comp_state == state.upper()).limit(50)
    if city:
        statement = statement.where(rental_comps.c.comp_city == city)
    if bedrooms is not None:
        try:
            bedroom_count = int(float(bedrooms))
            statement = statement.where(rental_comps.c.beds == bedroom_count)
        except (TypeError, ValueError):
            pass
    with get_property_engine().begin() as conn:
        rows = conn.execute(statement).mappings().all()
    return {
        "success": True,
        "strategy": "REALTIME_ONLY",
        "city": city,
        "state": state,
        "bedrooms": bedrooms,
        "comps": [_jsonable(_row_to_dict(row)) for row in rows],
        "message": (
            f"Found {len(rows)} saved provider/database rental comp(s)."
            if rows
            else "Realtime rental comps are unavailable until a live rental provider or imported comp dataset is connected."
        ),
    }


def data_priority() -> dict[str, Any]:
    return {
        "success": True,
        "strategy": {
            "countyData": True,
            "internalRentEngine": False,
            "section8Estimates": False,
            "cacheEnabled": True,
            "premiumApisLimited": True,
            "rentcastDisabled": True,
            "priorityOrder": [
                "County Assessor",
                "County GIS",
                "Tax Delinquency",
                "Foreclosure Filings",
                "HUD/Section 8 Rent Data when HUD_USER_TOKEN is configured",
                "Imported rental comp datasets",
                "Provider-backed MLS/Public Data",
                "Optional Premium APIs when explicitly enabled",
            ],
        },
    }
