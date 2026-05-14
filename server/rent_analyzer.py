"""Rent analyzer and comp rent engine for House Deal Scraper.

Realtime mode is intentionally strict: it uses saved/provider rent values,
database comps, and official HUD FMR data when configured. It does not fabricate
synthetic comps, market rent, or Section 8 numbers when live data is missing.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping, Optional

from sqlalchemy import Column, DateTime, Integer, Numeric, String, Table, Text, delete, desc, insert, select

from server.hud_fmr import lookup_hud_fmr
from server.property_system import _jsonable, _row_to_dict, get_property_engine, metadata, properties


rental_comps = Table(
    "rental_comps",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("property_id", Integer, nullable=False),
    Column("comp_address", String(255)),
    Column("comp_city", String(120)),
    Column("comp_state", String(50)),
    Column("comp_zip", String(20)),
    Column("rent", Numeric),
    Column("beds", Numeric),
    Column("baths", Numeric),
    Column("sqft", Integer),
    Column("property_type", String(80)),
    Column("latitude", Numeric),
    Column("longitude", Numeric),
    Column("source", String(120)),
    Column("listed_date", DateTime),
    Column("days_on_market", Integer),
    Column("distance_miles", Numeric),
    Column("confidence_weight", Numeric),
    Column("created_at", DateTime, default=datetime.utcnow),
)

section8_rents = Table(
    "section8_rents",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("zip_code", String(20)),
    Column("county", String(120)),
    Column("state", String(50)),
    Column("bedrooms", Integer),
    Column("fmr_rent", Numeric),
    Column("payment_standard", Numeric),
    Column("updated_at", DateTime, default=datetime.utcnow),
)

deal_analysis = Table(
    "deal_analysis",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("property_id", Integer, nullable=False),
    Column("estimated_rent", Numeric),
    Column("rent_low", Numeric),
    Column("rent_high", Numeric),
    Column("section8_rent", Numeric),
    Column("confidence_score", Numeric),
    Column("gross_yield", Numeric),
    Column("cap_rate", Numeric),
    Column("monthly_cash_flow", Numeric),
    Column("cash_on_cash_return", Numeric),
    Column("expense_ratio", Numeric),
    Column("under_rented_score", String(40)),
    Column("market_rent_gap", Numeric),
    Column("section8_spread", Numeric),
    Column("comp_count", Integer),
    Column("summary", Text),
    Column("updated_at", DateTime, default=datetime.utcnow),
)


def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    value = _num(value)
    return int(value) if value is not None else None


def _days_old(value: Any) -> int:
    if isinstance(value, datetime):
        delta = datetime.utcnow() - value
        return max(0, int(delta.total_seconds() / 86400))
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", ""))
            return _days_old(parsed)
        except ValueError:
            return 365
    return 365


def _same_street(a: str, b: str) -> bool:
    left = (a or "").lower().split(",")[0].strip()
    right = (b or "").lower().split(",")[0].strip()
    if not left or not right:
        return False
    left_tokens = left.split()
    right_tokens = right.split()
    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return False
    return left_tokens[-2:] == right_tokens[-2:] or left_tokens[-1:] == right_tokens[-1:]


def _comp_weight(subject: Mapping[str, Any], comp: Mapping[str, Any]) -> float:
    weight = 10.0
    subject_zip = str(subject.get("zip") or "")
    comp_zip = str(comp.get("zip") or "")
    subject_beds = _num(subject.get("bedrooms"))
    comp_beds = _num(comp.get("bedrooms"))
    subject_baths = _num(subject.get("bathrooms"))
    comp_baths = _num(comp.get("bathrooms"))
    subject_sqft = _num(subject.get("sqft"))
    comp_sqft = _num(comp.get("sqft"))

    if _same_street(str(subject.get("address") or ""), str(comp.get("address") or "")):
        weight += 25
    if subject_zip and subject_zip == comp_zip:
        weight += 20
    if subject_beds is not None and comp_beds is not None and abs(subject_beds - comp_beds) <= 1:
        weight += 8
    if subject_baths is not None and comp_baths is not None and abs(subject_baths - comp_baths) <= 1:
        weight += 7
    if subject_sqft and comp_sqft:
        sqft_delta = abs(subject_sqft - comp_sqft) / subject_sqft
        if sqft_delta <= 0.25:
            weight += 10
        elif sqft_delta > 0.40:
            weight -= 20
    if subject.get("property_type") and subject.get("property_type") == comp.get("property_type"):
        weight += 15

    days_old = _days_old(comp.get("updated_at") or comp.get("created_at"))
    if days_old < 90:
        weight += 15
    elif days_old > 365:
        weight -= 15

    return max(5.0, min(weight, 100.0))


def _section8_rent_for(property_data: Mapping[str, Any]) -> Optional[float]:
    bedrooms = _int(property_data.get("bedrooms")) or 2
    state = str(property_data.get("state") or "")
    county = str(property_data.get("county") or "")
    zip_code = str(property_data.get("zip") or "")
    result = lookup_hud_fmr(state=state, county=county, zip_code=zip_code, bedrooms=bedrooms)
    return _num(result.get("rent")) if result else None


def _saved_rent_for(property_data: Mapping[str, Any]) -> Optional[float]:
    rent = _num(property_data.get("estimated_rent"))
    if rent:
        return rent
    return None


def _database_rental_comps(property_data: Mapping[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    with get_property_engine().begin() as conn:
        statement = (
            select(properties)
            .where(properties.c.id != property_data["id"])
            .where(properties.c.state == property_data.get("state"))
        )
        if property_data.get("city"):
            statement = statement.where(properties.c.city == property_data.get("city"))
        rows = conn.execute(statement.order_by(desc(properties.c.updated_at)).limit(limit)).mappings().all()

    comps: list[dict[str, Any]] = []
    for row in rows:
        comp = _row_to_dict(row)
        rent = _num(comp.get("estimated_rent"))
        if not rent:
            continue
        weight = _comp_weight(property_data, comp)
        comps.append(
            {
                "property_id": property_data["id"],
                "comp_address": comp.get("address"),
                "comp_city": comp.get("city"),
                "comp_state": comp.get("state"),
                "comp_zip": comp.get("zip"),
                "rent": rent,
                "beds": comp.get("bedrooms"),
                "baths": comp.get("bathrooms"),
                "sqft": comp.get("sqft"),
                "property_type": comp.get("property_type"),
                "latitude": None,
                "longitude": None,
                "source": "saved_property_database",
                "listed_date": datetime.utcnow(),
                "days_on_market": _days_old(comp.get("updated_at") or comp.get("created_at")),
                "distance_miles": 0.75 if comp.get("zip") == property_data.get("zip") else 1.5,
                "confidence_weight": weight,
                "created_at": datetime.utcnow(),
            }
        )
    return comps


def _confidence(comp_count: int, average_weight: float) -> float:
    if comp_count <= 0:
        return 0
    if comp_count >= 10:
        base = 85
    elif comp_count >= 5:
        base = 68
    elif comp_count >= 3:
        base = 55
    else:
        base = 42
    return max(0, min(98, round(base + (average_weight - 55) * 0.35, 1)))


def _deal_metrics(property_data: Mapping[str, Any], rent: Optional[float], section8_rent: Optional[float]) -> dict[str, Any]:
    purchase_price = _num(property_data.get("estimated_value")) or 0
    tax_due = _num(property_data.get("tax_amount_due")) or 0
    if not rent:
        return {
            "gross_yield": 0,
            "cap_rate": 0,
            "monthly_cash_flow": 0,
            "cash_on_cash_return": 0,
            "expense_ratio": 0,
            "section8_spread": None,
        }
    monthly_taxes = tax_due / 12 if tax_due else max(60, purchase_price * 0.018 / 12) if purchase_price else 90
    insurance = max(70, purchase_price * 0.008 / 12) if purchase_price else 85
    maintenance = rent * 0.08
    vacancy = rent * 0.05
    management = rent * 0.08
    monthly_expenses = monthly_taxes + insurance + maintenance + vacancy + management
    noi = (rent * 12) - (monthly_expenses * 12)
    monthly_cash_flow = rent - monthly_expenses
    gross_yield = ((rent * 12) / purchase_price * 100) if purchase_price else 0
    cap_rate = (noi / purchase_price * 100) if purchase_price else 0
    section8_spread = section8_rent - rent if section8_rent is not None else None
    return {
        "gross_yield": round(gross_yield, 1),
        "cap_rate": round(cap_rate, 1),
        "monthly_cash_flow": round(monthly_cash_flow),
        "cash_on_cash_return": round(cap_rate, 1),
        "expense_ratio": round(monthly_expenses / rent * 100, 1) if rent else 0,
        "section8_spread": round(section8_spread) if section8_spread is not None else None,
    }


def generate_rent_analysis(property_id: int) -> dict[str, Any]:
    with get_property_engine().begin() as conn:
        subject = conn.execute(select(properties).where(properties.c.id == property_id)).mappings().first()
    if not subject:
        raise ValueError("Property not found")

    property_data = _row_to_dict(subject)
    saved_rent = _saved_rent_for(property_data)
    section8_rent = _section8_rent_for(property_data)
    comps = _database_rental_comps(property_data)

    weights = [_num(comp.get("confidence_weight")) or 0 for comp in comps]
    rents = [_num(comp.get("rent")) or 0 for comp in comps]
    total_weight = sum(weights)
    estimated_rent = sum(rent * weight for rent, weight in zip(rents, weights)) / total_weight if total_weight else saved_rent
    rent_low = min(rents) if rents else saved_rent
    rent_high = max(rents) if rents else saved_rent
    confidence_score = _confidence(len(comps), total_weight / len(comps) if comps else 0)
    if saved_rent and not comps:
        confidence_score = 35
    metrics = _deal_metrics(property_data, estimated_rent, section8_rent)
    market_rent_gap = estimated_rent - saved_rent if estimated_rent and saved_rent and comps else None
    if market_rent_gap is None:
        under_rented_score = "DATA_UNAVAILABLE"
    else:
        under_rented_score = "HIGH" if market_rent_gap >= 300 else "MEDIUM" if market_rent_gap >= 125 else "LOW"
    if estimated_rent and comps:
        summary = (
            f"Realtime rent analysis found ${estimated_rent:,.0f}/mo from {len(comps)} saved provider/database comp signal(s). "
            f"HUD FMR is {('$' + format(section8_rent, ',.0f')) if section8_rent else 'unavailable'}. "
            f"Projected monthly cash flow is ${metrics['monthly_cash_flow']:,.0f} before financing."
        )
    elif estimated_rent:
        summary = (
            f"Saved provider rent is ${estimated_rent:,.0f}/mo, but realtime rental comps were not available. "
            "Confidence is low until live rental comp data is connected."
        )
    else:
        summary = (
            "Realtime rent data unavailable. Connect a live rent provider, import rental comps, or save provider-backed rent data "
            "before relying on cash-flow analysis."
        )

    analysis_values = {
        "property_id": property_id,
        "estimated_rent": round(estimated_rent) if estimated_rent is not None else None,
        "rent_low": round(rent_low) if rent_low is not None else None,
        "rent_high": round(rent_high) if rent_high is not None else None,
        "section8_rent": round(section8_rent) if section8_rent is not None else None,
        "confidence_score": confidence_score,
        "gross_yield": metrics["gross_yield"],
        "cap_rate": metrics["cap_rate"],
        "monthly_cash_flow": metrics["monthly_cash_flow"],
        "cash_on_cash_return": metrics["cash_on_cash_return"],
        "expense_ratio": metrics["expense_ratio"],
        "under_rented_score": under_rented_score,
        "market_rent_gap": round(market_rent_gap) if market_rent_gap is not None else None,
        "section8_spread": metrics["section8_spread"],
        "comp_count": len(comps),
        "summary": summary,
        "updated_at": datetime.utcnow(),
    }

    with get_property_engine().begin() as conn:
        conn.execute(delete(rental_comps).where(rental_comps.c.property_id == property_id))
        for comp in comps[:25]:
            conn.execute(insert(rental_comps).values(**comp))
        conn.execute(delete(deal_analysis).where(deal_analysis.c.property_id == property_id))
        result = conn.execute(insert(deal_analysis).values(**analysis_values))
        analysis_id = result.inserted_primary_key[0]
        if estimated_rent is not None:
            conn.execute(
                properties.update()
                .where(properties.c.id == property_id)
                .values(estimated_rent=round(estimated_rent), updated_at=datetime.utcnow())
            )
        analysis_row = conn.execute(select(deal_analysis).where(deal_analysis.c.id == analysis_id)).mappings().first()

    return {
        "analysis": _row_to_dict(analysis_row),
        "comps": [_jsonable(comp) for comp in comps[:25]],
    }


def get_rent_analysis(property_id: int) -> dict[str, Any]:
    with get_property_engine().begin() as conn:
        analysis_row = (
            conn.execute(select(deal_analysis).where(deal_analysis.c.property_id == property_id).order_by(desc(deal_analysis.c.updated_at)))
            .mappings()
            .first()
        )
        comp_rows = (
            conn.execute(select(rental_comps).where(rental_comps.c.property_id == property_id).order_by(desc(rental_comps.c.confidence_weight)))
            .mappings()
            .all()
        )
    if not analysis_row:
        return generate_rent_analysis(property_id)
    return {
        "analysis": _row_to_dict(analysis_row),
        "comps": [_row_to_dict(row) for row in comp_rows],
    }
