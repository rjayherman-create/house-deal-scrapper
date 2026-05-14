"""AI deal hunter and market discovery engine.

V1 keeps this intentionally lean: it derives market stats from the existing
property database and rent-analysis tables, scores properties, and creates
discovery alerts for cash-flow, Section 8, foreclosure, and hidden-market
opportunities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, Numeric, String, Table, Text, delete, desc, insert, select

from server.low_cost_data_engine import estimate_section8_rent
from server.property_system import _jsonable, _row_to_dict, get_property_engine, metadata, properties
from server.rent_analyzer import deal_analysis


market_stats = Table(
    "market_stats",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("city", Text),
    Column("state", Text),
    Column("zip_code", Text),
    Column("avg_price", Numeric),
    Column("median_price", Numeric),
    Column("avg_rent", Numeric),
    Column("median_rent", Numeric),
    Column("avg_section8_rent", Numeric),
    Column("vacancy_rate", Numeric),
    Column("foreclosure_rate", Numeric),
    Column("crime_score", Numeric),
    Column("appreciation_score", Numeric),
    Column("investor_activity_score", Numeric),
    Column("permit_growth_score", Numeric),
    Column("population_growth_score", Numeric),
    Column("cashflow_score", Numeric),
    Column("opportunity_score", Numeric),
    Column("discovered_by_ai", Boolean, default=False),
    Column("updated_at", DateTime, default=datetime.utcnow),
)

property_scores = Table(
    "property_scores",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("property_id", Integer, nullable=False),
    Column("cashflow_score", Numeric),
    Column("rehab_score", Numeric),
    Column("section8_score", Numeric),
    Column("neighborhood_score", Numeric),
    Column("appreciation_score", Numeric),
    Column("competition_score", Numeric),
    Column("risk_score", Numeric),
    Column("total_score", Numeric),
    Column("ai_reasoning", JSON),
    Column("created_at", DateTime, default=datetime.utcnow),
)

discovery_alerts = Table(
    "discovery_alerts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", Text),
    Column("description", Text),
    Column("city", Text),
    Column("state", Text),
    Column("alert_type", Text),
    Column("score", Numeric),
    Column("payload", JSON),
    Column("created_at", DateTime, default=datetime.utcnow),
)

user_preferences = Table(
    "user_preferences",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer),
    Column("max_price", Numeric),
    Column("min_roi", Numeric),
    Column("section8_enabled", Boolean, default=True),
    Column("preferred_states", JSON),
    Column("preferred_property_types", JSON),
    Column("crime_tolerance", Numeric),
    Column("rehab_tolerance", Numeric),
    Column("created_at", DateTime, default=datetime.utcnow),
)


TARGET_MARKETS = [
    {"city": "Buffalo", "state": "NY", "zip_code": "", "latitude": 42.8864, "longitude": -78.8784},
    {"city": "Rochester", "state": "NY", "zip_code": "", "latitude": 43.1566, "longitude": -77.6088},
    {"city": "Syracuse", "state": "NY", "zip_code": "", "latitude": 43.0481, "longitude": -76.1474},
    {"city": "Cleveland", "state": "OH", "zip_code": "", "latitude": 41.4993, "longitude": -81.6944},
    {"city": "Toledo", "state": "OH", "zip_code": "", "latitude": 41.6528, "longitude": -83.5379},
    {"city": "Detroit", "state": "MI", "zip_code": "", "latitude": 42.3314, "longitude": -83.0458},
    {"city": "Peoria", "state": "IL", "zip_code": "", "latitude": 40.6936, "longitude": -89.5890},
    {"city": "Youngstown", "state": "OH", "zip_code": "", "latitude": 41.0998, "longitude": -80.6495},
]

MARKET_COORDS = {
    (item["city"], item["state"]): (item["latitude"], item["longitude"])
    for item in TARGET_MARKETS
}


def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _median(values: list[float]) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _score_market(rows: list[Mapping[str, Any]], city: str, state: str, zip_code: str) -> dict[str, Any]:
    prices = [_num(row.get("estimated_value")) for row in rows]
    prices = [value for value in prices if value]
    rents = [_num(row.get("estimated_rent")) for row in rows]
    rents = [value for value in rents if value]
    bedrooms = [_num(row.get("bedrooms")) or 2 for row in rows]
    avg_price = sum(prices) / len(prices) if prices else 0
    avg_rent = sum(rents) / len(rents) if rents else 0
    avg_section8 = sum(estimate_section8_rent(bed, city, state) for bed in bedrooms) / len(bedrooms) if bedrooms else estimate_section8_rent(2, city, state)
    foreclosure_rate = 100 * sum(1 for row in rows if row.get("foreclosure")) / len(rows) if rows else 0
    vacancy_rate = 100 * sum(1 for row in rows if row.get("vacant")) / len(rows) if rows else 0
    investor_activity = min(10, len(rows) / 8)
    rent_to_price = (avg_rent * 12 / avg_price) if avg_price else 0
    cashflow_score = min(100, rent_to_price * 520)
    section8_bonus = max(0, (avg_section8 - avg_rent) / avg_rent * 100) if avg_rent else 0
    opportunity_score = min(100, cashflow_score + section8_bonus + max(0, 10 - investor_activity) * 2 + min(15, foreclosure_rate))
    return {
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "avg_price": round(avg_price),
        "median_price": round(_median(prices)),
        "avg_rent": round(avg_rent),
        "median_rent": round(_median(rents)),
        "avg_section8_rent": round(avg_section8),
        "vacancy_rate": round(vacancy_rate, 1),
        "foreclosure_rate": round(foreclosure_rate, 1),
        "crime_score": 5,
        "appreciation_score": 6 if opportunity_score >= 55 else 4,
        "investor_activity_score": round(investor_activity, 1),
        "permit_growth_score": 5,
        "population_growth_score": 5,
        "cashflow_score": round(cashflow_score, 1),
        "opportunity_score": round(opportunity_score, 1),
        "discovered_by_ai": opportunity_score >= 60,
        "updated_at": datetime.utcnow(),
    }


def update_market_stats() -> list[dict[str, Any]]:
    with get_property_engine().begin() as conn:
        rows = conn.execute(select(properties)).mappings().all()
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        item = _row_to_dict(row)
        key = (
            str(item.get("city") or "Unknown"),
            str(item.get("state") or ""),
            str(item.get("zip") or ""),
        )
        groups.setdefault(key, []).append(item)

    stats = [_score_market(group_rows, *key) for key, group_rows in groups.items() if key[1]]
    with get_property_engine().begin() as conn:
        conn.execute(delete(market_stats))
        for stat in stats:
            conn.execute(insert(market_stats).values(**stat))
    return [_jsonable(stat) for stat in sorted(stats, key=lambda item: item["opportunity_score"], reverse=True)]


def calculate_property_ai_score(property_data: Mapping[str, Any], market: Mapping[str, Any], rent_analysis: Mapping[str, Any]) -> dict[str, Any]:
    reasons = []
    price = _num(property_data.get("estimated_value")) or 0
    rent = _num(rent_analysis.get("estimated_rent") or property_data.get("estimated_rent")) or 0
    section8 = _num(rent_analysis.get("section8_rent") or market.get("avg_section8_rent")) or 0
    market_avg_price = _num(market.get("avg_price")) or price
    investor_activity = _num(market.get("investor_activity_score")) or 5
    appreciation = _num(market.get("appreciation_score")) or 5
    vacancy = _num(market.get("vacancy_rate")) or 10

    cashflow_score = 0
    section8_score = 0
    neighborhood_score = 45
    appreciation_score = appreciation * 10
    competition_score = max(0, (10 - investor_activity) * 10)
    risk_score = 25

    if price and market_avg_price and price < market_avg_price * 0.65:
        reasons.append("Price significantly below market average")
        cashflow_score += 20
    if price and rent:
        rent_ratio = rent / price
        if rent_ratio > 0.02:
            reasons.append("Strong rent-to-price ratio")
            cashflow_score += 25
        elif rent_ratio > 0.015:
            cashflow_score += 15
    if section8 and rent and section8 > rent:
        reasons.append("Section 8 rents exceed market rent")
        section8_score += 15
    if investor_activity < 4:
        reasons.append("Low investor competition")
        competition_score += 15
    if appreciation > 7:
        reasons.append("Neighborhood appreciation improving")
    if vacancy < 5:
        reasons.append("Vacancy rates improving")
        neighborhood_score += 10
    if property_data.get("foreclosure") or property_data.get("tax_delinquent"):
        reasons.append("Distress indicator may create acquisition leverage")
        risk_score += 10

    total_score = min(100, cashflow_score + section8_score + (neighborhood_score * 0.2) + (appreciation_score * 0.1) + (competition_score * 0.15) - (risk_score * 0.12))
    return {
        "property_id": property_data["id"],
        "cashflow_score": round(cashflow_score, 1),
        "rehab_score": 50,
        "section8_score": round(section8_score, 1),
        "neighborhood_score": round(neighborhood_score, 1),
        "appreciation_score": round(appreciation_score, 1),
        "competition_score": round(competition_score, 1),
        "risk_score": round(risk_score, 1),
        "total_score": round(max(0, total_score), 1),
        "ai_reasoning": {"reasons": reasons or ["Score uses price, rent, Section 8, competition, and market momentum signals."]},
        "created_at": datetime.utcnow(),
    }


def calculate_all_property_scores() -> list[dict[str, Any]]:
    with get_property_engine().begin() as conn:
        property_rows = conn.execute(select(properties)).mappings().all()
        stat_rows = conn.execute(select(market_stats)).mappings().all()
        rent_rows = conn.execute(select(deal_analysis).order_by(desc(deal_analysis.c.updated_at))).mappings().all()

    market_by_key = {(row.get("city"), row.get("state"), row.get("zip_code")): _row_to_dict(row) for row in stat_rows}
    rent_by_property: dict[int, dict[str, Any]] = {}
    for row in rent_rows:
        item = _row_to_dict(row)
        rent_by_property.setdefault(int(item["property_id"]), item)

    scores = []
    for row in property_rows:
        property_data = _row_to_dict(row)
        key = (property_data.get("city"), property_data.get("state"), property_data.get("zip"))
        market = market_by_key.get(key) or {}
        scores.append(calculate_property_ai_score(property_data, market, rent_by_property.get(int(property_data["id"]), {})))

    with get_property_engine().begin() as conn:
        conn.execute(delete(property_scores))
        for score in scores:
            conn.execute(insert(property_scores).values(**score))
    return [_jsonable(score) for score in sorted(scores, key=lambda item: item["total_score"], reverse=True)]


def _enabled_filter(filters: Optional[Mapping[str, Any]], key: str) -> bool:
    if not filters:
        return True
    return bool(filters.get(key, True))


def _alert_type_for_reason(reason: str) -> str:
    lower = reason.lower()
    if "section 8" in lower:
        return "section8_arbitrage"
    if "foreclosure" in lower:
        return "rising_foreclosure_inventory"
    if "cash flow" in lower:
        return "high_cash_flow_area"
    if "undervalued" in lower:
        return "undervalued_zip"
    if "appreciation" in lower:
        return "emerging_appreciation_market"
    return "ai_hidden_market"


def run_market_discovery(filters: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    stats = update_market_stats()
    scores = calculate_all_property_scores()
    alerts = []
    for market in stats:
        reasons = []
        avg_price = _num(market.get("avg_price")) or 0
        avg_rent = _num(market.get("avg_rent")) or 0
        section8 = _num(market.get("avg_section8_rent")) or 0
        rent_to_price = (avg_rent * 12 / avg_price) if avg_price else 0
        if _enabled_filter(filters, "cashflow") and rent_to_price > 0.018 and (_num(market.get("investor_activity_score")) or 10) < 5 and (_num(market.get("vacancy_rate")) or 10) < 8:
            reasons.append("Strong cash flow with low competition")
        if _enabled_filter(filters, "section8") and avg_rent and section8 > avg_rent * 1.15:
            reasons.append("Section 8 arbitrage opportunity")
        if _enabled_filter(filters, "foreclosure") and (_num(market.get("foreclosure_rate")) or 0) > 7 and (_num(market.get("investor_activity_score")) or 10) < 4:
            reasons.append("Foreclosure inventory increasing")
        if _enabled_filter(filters, "undervalued") and avg_price and avg_price < 85000 and rent_to_price > 0.014:
            reasons.append("Undervalued ZIP code with useful rent support")
        if _enabled_filter(filters, "appreciation") and (_num(market.get("appreciation_score")) or 0) >= 6 and (_num(market.get("opportunity_score")) or 0) >= 55:
            reasons.append("Emerging appreciation market with cash-flow support")
        if _enabled_filter(filters, "hidden") and not reasons and (_num(market.get("opportunity_score")) or 0) >= 60:
            reasons.append("AI hidden market score crossed opportunity threshold")
        for reason in reasons:
            alert_type = _alert_type_for_reason(reason)
            alerts.append(
                {
                    "title": "AI Market Discovery",
                    "description": reason,
                    "city": market.get("city"),
                    "state": market.get("state"),
                    "alert_type": alert_type,
                    "score": market.get("opportunity_score"),
                    "payload": {"market": market, "reasons": reasons},
                    "created_at": datetime.utcnow(),
                }
            )

    with get_property_engine().begin() as conn:
        conn.execute(delete(discovery_alerts))
        for alert in alerts:
            conn.execute(insert(discovery_alerts).values(**alert))

    return {
        "success": True,
        "markets": stats[:25],
        "property_scores": scores[:50],
        "alerts": [_jsonable(alert) for alert in sorted(alerts, key=lambda item: item["score"] or 0, reverse=True)[:50]],
    }


def get_market_stats(limit: int = 50) -> list[dict[str, Any]]:
    with get_property_engine().begin() as conn:
        rows = conn.execute(select(market_stats).order_by(desc(market_stats.c.opportunity_score)).limit(limit)).mappings().all()
    return [_row_to_dict(row) for row in rows]


def get_discovery_alerts(limit: int = 50) -> list[dict[str, Any]]:
    with get_property_engine().begin() as conn:
        rows = conn.execute(select(discovery_alerts).order_by(desc(discovery_alerts.c.score), desc(discovery_alerts.c.created_at)).limit(limit)).mappings().all()
    return [_row_to_dict(row) for row in rows]


def get_target_markets() -> list[dict[str, Any]]:
    stats = get_market_stats(250)
    covered = {(item.get("city"), item.get("state")) for item in stats}
    return [
        {
            **market,
            "coverage": "active" if (market["city"], market["state"]) in covered else "target",
            "reason": "Low acquisition cost, Section 8 demand, high cash-flow potential, or low investor saturation.",
        }
        for market in TARGET_MARKETS
    ]


def get_market_heatmap_geojson(limit: int = 100) -> dict[str, Any]:
    features = []
    for market in get_market_stats(limit):
        coords = MARKET_COORDS.get((market.get("city"), market.get("state")))
        if not coords:
            continue
        latitude, longitude = coords
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
                "properties": {
                    **market,
                    "weight": market.get("opportunity_score") or 0,
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
    }


def get_ai_recommendations(
    max_price: Optional[float] = None,
    preferred_states: Optional[list[str]] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    scores = calculate_all_property_scores()
    score_by_property_id = {int(score["property_id"]): score for score in scores}
    with get_property_engine().begin() as conn:
        rows = conn.execute(select(properties)).mappings().all()
    recommendations = []
    preferred_state_set = {state.upper() for state in preferred_states or [] if state}
    for row in rows:
        item = _row_to_dict(row)
        price = _num(item.get("estimated_value")) or 0
        state = str(item.get("state") or "").upper()
        if max_price is not None and price and price > max_price:
            continue
        if preferred_state_set and state not in preferred_state_set:
            continue
        score = score_by_property_id.get(int(item["id"]), {})
        item["aiScore"] = score.get("total_score", item.get("deal_score", 0))
        item["aiReasoning"] = score.get("ai_reasoning", {})
        recommendations.append(item)
    recommendations.sort(key=lambda item: item.get("aiScore") or 0, reverse=True)
    return recommendations[:limit]
