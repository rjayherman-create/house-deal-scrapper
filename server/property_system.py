"""
Property intelligence storage and APIs for House Deal Scraper.

This module is the Python/FastAPI equivalent of the requested Express + Drizzle
foundation block. It uses PostgreSQL when DATABASE_URL is configured on Railway,
and falls back to SQLite for local development.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    create_engine,
    desc,
    select,
    text as sql_text,
    update,
)
from sqlalchemy.engine import Engine, RowMapping

logger = logging.getLogger(__name__)

metadata = MetaData()
_engine: Optional[Engine] = None


properties = Table(
    "properties",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("address", String(255), nullable=False),
    Column("city", String(120)),
    Column("state", String(50)),
    Column("zip", String(20)),
    Column("county", String(120)),
    Column("parcel_id", String(120)),
    Column("property_type", String(80)),
    Column("bedrooms", Integer),
    Column("bathrooms", Numeric),
    Column("sqft", Integer),
    Column("lot_size", Integer),
    Column("year_built", Integer),
    Column("estimated_value", Numeric),
    Column("estimated_rent", Numeric),
    Column("tax_delinquent", Boolean, default=False),
    Column("tax_amount_due", Numeric),
    Column("owner_name", String(255)),
    Column("absentee_owner", Boolean, default=False),
    Column("vacant", Boolean, default=False),
    Column("foreclosure", Boolean, default=False),
    Column("probate", Boolean, default=False),
    Column("code_violations", Boolean, default=False),
    Column("deal_score", Integer, default=0),
    Column("ai_summary", Text),
    Column("status", String(80), default="SCRAPED"),
    Column("source_listing_id", Integer),
    Column("created_at", DateTime, default=datetime.utcnow),
    Column("updated_at", DateTime, default=datetime.utcnow),
)

property_snapshots = Table(
    "property_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("property_id", Integer, nullable=False),
    Column("snapshot_date", DateTime, default=datetime.utcnow),
    Column("estimated_value", Numeric),
    Column("tax_amount_due", Numeric),
    Column("owner_name", String(255)),
    Column("foreclosure", Boolean),
    Column("vacant", Boolean),
    Column("raw_data", JSON),
)

watchlists = Table(
    "watchlists",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("property_id", Integer, nullable=False),
    Column("user_id", String(255), nullable=False),
    Column("created_at", DateTime, default=datetime.utcnow),
)

property_notes = Table(
    "property_notes",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("property_id", Integer, nullable=False),
    Column("user_id", String(255)),
    Column("note", Text),
    Column("created_at", DateTime, default=datetime.utcnow),
)


def _database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    db_path = os.getenv("DISTRESSIQ_DB_PATH", "distressiq.db")
    return f"sqlite:///{db_path}"


def get_property_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(_database_url(), pool_pre_ping=True, future=True)
    return _engine


def init_property_system_db() -> None:
    """Create missing property intelligence tables without dropping data."""

    try:
        engine = get_property_engine()
        metadata.create_all(engine)
        ensure_property_system_columns(engine)
        logger.info("property intelligence tables are ready")
    except Exception as exc:
        logger.exception("property intelligence database init failed: %s", exc)


PROPERTY_SYSTEM_COLUMNS: dict[str, dict[str, str]] = {
    "properties": {
        "address": "VARCHAR(255)",
        "city": "VARCHAR(120)",
        "state": "VARCHAR(50)",
        "zip": "VARCHAR(20)",
        "county": "VARCHAR(120)",
        "parcel_id": "VARCHAR(120)",
        "property_type": "VARCHAR(80)",
        "bedrooms": "INTEGER",
        "bathrooms": "NUMERIC",
        "sqft": "INTEGER",
        "lot_size": "INTEGER",
        "year_built": "INTEGER",
        "estimated_value": "NUMERIC",
        "estimated_rent": "NUMERIC",
        "tax_delinquent": "BOOLEAN",
        "tax_amount_due": "NUMERIC",
        "owner_name": "VARCHAR(255)",
        "absentee_owner": "BOOLEAN",
        "vacant": "BOOLEAN",
        "foreclosure": "BOOLEAN",
        "probate": "BOOLEAN",
        "code_violations": "BOOLEAN",
        "deal_score": "INTEGER",
        "ai_summary": "TEXT",
        "status": "VARCHAR(80)",
        "source_listing_id": "INTEGER",
        "created_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    },
    "property_snapshots": {
        "property_id": "INTEGER",
        "snapshot_date": "TIMESTAMP",
        "estimated_value": "NUMERIC",
        "tax_amount_due": "NUMERIC",
        "owner_name": "VARCHAR(255)",
        "foreclosure": "BOOLEAN",
        "vacant": "BOOLEAN",
        "raw_data": "JSON",
    },
    "watchlists": {
        "property_id": "INTEGER",
        "user_id": "VARCHAR(255)",
        "created_at": "TIMESTAMP",
    },
    "property_notes": {
        "property_id": "INTEGER",
        "user_id": "VARCHAR(255)",
        "note": "TEXT",
        "created_at": "TIMESTAMP",
    },
}


def ensure_property_system_columns(engine: Engine) -> None:
    """Add missing columns on existing deployments without wiping tables."""

    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            for table_name, columns in PROPERTY_SYSTEM_COLUMNS.items():
                for column_name, column_type in columns.items():
                    conn.execute(
                        sql_text(
                            f"ALTER TABLE {table_name} "
                            f"ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
                        )
                    )
            return

        if dialect == "sqlite":
            for table_name, columns in PROPERTY_SYSTEM_COLUMNS.items():
                existing = {
                    row[1]
                    for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
                }
                for column_name, column_type in columns.items():
                    if column_name not in existing:
                        conn.exec_driver_sql(
                            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                        )


def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    parsed = _num(value)
    return int(parsed) if parsed is not None else None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _row_to_dict(row: RowMapping[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in row.items()}


def calculate_deal_score(property_data: Mapping[str, Any]) -> int:
    score = 0

    if _bool(property_data.get("taxDelinquent") or property_data.get("tax_delinquent")):
        score += 20
    if _bool(property_data.get("vacant")):
        score += 20
    if _bool(property_data.get("foreclosure")):
        score += 25
    if _bool(property_data.get("absenteeOwner") or property_data.get("absentee_owner")):
        score += 10
    if _bool(property_data.get("codeViolations") or property_data.get("code_violations")):
        score += 10
    if _bool(property_data.get("probate")):
        score += 10

    estimated_value = _num(property_data.get("estimatedValue") or property_data.get("estimated_value"))
    estimated_rent = _num(property_data.get("estimatedRent") or property_data.get("estimated_rent"))
    if estimated_value and estimated_rent:
        ratio = (estimated_rent * 12) / estimated_value
        if ratio >= 0.15:
            score += 25
        elif ratio >= 0.12:
            score += 15
        elif ratio >= 0.10:
            score += 10

    analysis_score = _num(property_data.get("analysisDealScore"))
    if analysis_score is not None:
        score = max(score, round(analysis_score * 100 if analysis_score <= 1 else analysis_score))

    return min(score, 100)


def build_ai_summary(property_data: Mapping[str, Any], deal_score: int) -> str:
    indicators = []
    if _bool(property_data.get("taxDelinquent") or property_data.get("tax_delinquent")):
        indicators.append("- Tax delinquent")
    if _bool(property_data.get("vacant")):
        indicators.append("- Vacant")
    if _bool(property_data.get("foreclosure")):
        indicators.append("- Foreclosure risk")
    if _bool(property_data.get("absenteeOwner") or property_data.get("absentee_owner")):
        indicators.append("- Absentee owner")
    if _bool(property_data.get("codeViolations") or property_data.get("code_violations")):
        indicators.append("- Code violations")
    if _bool(property_data.get("probate")):
        indicators.append("- Probate")

    indicator_text = "\n".join(indicators) if indicators else "- No major distress flags confirmed yet"
    return (
        "Potential distressed opportunity.\n\n"
        f"Indicators:\n{indicator_text}\n\n"
        f"Estimated value: ${_num(property_data.get('estimatedValue') or property_data.get('estimated_value')) or 0:,.0f}\n"
        f"Estimated rent: ${_num(property_data.get('estimatedRent') or property_data.get('estimated_rent')) or 0:,.0f}\n\n"
        f"Deal Score: {deal_score}/100"
    )


def _property_values(data: Mapping[str, Any], deal_score: int, ai_summary: str) -> dict[str, Any]:
    return {
        "address": _first(data, "address", "propertyAddress") or "Unknown address",
        "city": _first(data, "city"),
        "state": _first(data, "state"),
        "zip": _first(data, "zip", "zipCode", "zip_code"),
        "county": _first(data, "county"),
        "parcel_id": _first(data, "parcelId", "parcel_id", "apn"),
        "property_type": _first(data, "propertyType", "property_type"),
        "bedrooms": _int(_first(data, "bedrooms", "beds")),
        "bathrooms": _num(_first(data, "bathrooms", "baths")),
        "sqft": _int(_first(data, "sqft", "squareFootage", "square_footage")),
        "lot_size": _int(_first(data, "lotSize", "lot_size")),
        "year_built": _int(_first(data, "yearBuilt", "year_built")),
        "estimated_value": _num(_first(data, "estimatedValue", "estimated_value")),
        "estimated_rent": _num(_first(data, "estimatedRent", "estimated_rent")),
        "tax_delinquent": _bool(_first(data, "taxDelinquent", "tax_delinquent")),
        "tax_amount_due": _num(_first(data, "taxAmountDue", "tax_amount_due")),
        "owner_name": _first(data, "ownerName", "owner_name"),
        "absentee_owner": _bool(_first(data, "absenteeOwner", "absentee_owner")),
        "vacant": _bool(data.get("vacant")),
        "foreclosure": _bool(data.get("foreclosure")),
        "probate": _bool(data.get("probate")),
        "code_violations": _bool(_first(data, "codeViolations", "code_violations")),
        "deal_score": deal_score,
        "ai_summary": ai_summary,
        "status": _first(data, "status") or "SCRAPED",
        "source_listing_id": _int(_first(data, "sourceListingId", "source_listing_id")),
        "updated_at": datetime.utcnow(),
    }


def ingest_property(data: Mapping[str, Any]) -> dict[str, Any]:
    deal_score = calculate_deal_score(data)
    ai_summary = build_ai_summary(data, deal_score)
    values = _property_values(data, deal_score, ai_summary)
    values["created_at"] = datetime.utcnow()

    engine = get_property_engine()
    with engine.begin() as conn:
        result = conn.execute(properties.insert().values(**values))
        property_id = result.inserted_primary_key[0]
        conn.execute(
            property_snapshots.insert().values(
                property_id=property_id,
                estimated_value=values["estimated_value"],
                tax_amount_due=values["tax_amount_due"],
                owner_name=values["owner_name"],
                foreclosure=values["foreclosure"],
                vacant=values["vacant"],
                raw_data=_jsonable(data),
            )
        )
        row = conn.execute(select(properties).where(properties.c.id == property_id)).mappings().first()

    return _row_to_dict(row) if row else {"id": property_id, **_jsonable(values)}


def _estimate_from(raw: Mapping[str, Any], *sections: str) -> Optional[float]:
    for section_name in sections:
        section = raw.get(section_name)
        if not isinstance(section, Mapping):
            continue
        value = _first(section, "price", "value", "estimatedValue", "median", "rent")
        parsed = _num(value)
        if parsed is not None:
            return parsed
    return None


def ingest_property_from_analysis(analysis: Any, source_listing_id: Optional[int] = None) -> dict[str, Any]:
    listing = analysis.listing
    raw = listing.raw_data or {}
    property_record = raw.get("property_record") if isinstance(raw.get("property_record"), Mapping) else {}
    merged = {
        "address": listing.address,
        "city": listing.city,
        "state": listing.state,
        "zip_code": _first(raw, "zip_code", "zipCode", "postalCode"),
        "county": _first(property_record, "county", "countyName"),
        "parcelId": _first(property_record, "id", "parcelId", "parcel_id", "apn", "assessorID"),
        "propertyType": _first(property_record, "propertyType", "property_type"),
        "bedrooms": listing.beds or _first(property_record, "bedrooms"),
        "bathrooms": listing.baths or _first(property_record, "bathrooms"),
        "sqft": listing.sqft or _first(property_record, "squareFootage", "sqft"),
        "lotSize": _first(property_record, "lotSize", "lot_size"),
        "yearBuilt": listing.year_built or _first(property_record, "yearBuilt", "year_built"),
        "estimatedValue": _estimate_from(raw, "value_estimate") or listing.price,
        "estimatedRent": _estimate_from(raw, "rent_estimate"),
        "taxAmountDue": _first(property_record, "taxAmountDue", "tax_amount_due"),
        "ownerName": _first(property_record, "ownerName", "owner_name"),
        "vacant": _first(raw, "vacant") or False,
        "foreclosure": _first(raw, "foreclosure") or False,
        "taxDelinquent": _first(raw, "taxDelinquent", "tax_delinquent") or False,
        "absenteeOwner": _first(raw, "absenteeOwner", "absentee_owner") or False,
        "codeViolations": _first(raw, "codeViolations", "code_violations") or False,
        "probate": _first(raw, "probate") or False,
        "analysisDealScore": analysis.deal_scores.final_score,
        "status": "ANALYZED",
        "sourceListingId": source_listing_id,
        "raw_listing": raw,
        "analysis": _jsonable(analysis),
    }
    return ingest_property(merged)


def get_high_deals(limit: int = 100) -> list[dict[str, Any]]:
    with get_property_engine().begin() as conn:
        rows = (
            conn.execute(select(properties).order_by(desc(properties.c.deal_score)).limit(limit))
            .mappings()
            .all()
        )
    return [_row_to_dict(row) for row in rows]


def get_property_detail(property_id: int) -> dict[str, Any]:
    with get_property_engine().begin() as conn:
        property_row = (
            conn.execute(select(properties).where(properties.c.id == property_id))
            .mappings()
            .first()
        )
        snapshots = (
            conn.execute(
                select(property_snapshots)
                .where(property_snapshots.c.property_id == property_id)
                .order_by(desc(property_snapshots.c.snapshot_date))
            )
            .mappings()
            .all()
        )
        notes = (
            conn.execute(select(property_notes).where(property_notes.c.property_id == property_id))
            .mappings()
            .all()
        )

    return {
        "property": _row_to_dict(property_row) if property_row else None,
        "snapshots": [_row_to_dict(row) for row in snapshots],
        "notes": [_row_to_dict(row) for row in notes],
    }


def add_to_watchlist(property_id: int, user_id: str) -> None:
    with get_property_engine().begin() as conn:
        conn.execute(watchlists.insert().values(property_id=property_id, user_id=user_id))


def add_property_note(property_id: int, user_id: Optional[str], note: str) -> None:
    with get_property_engine().begin() as conn:
        conn.execute(
            property_notes.insert().values(
                property_id=property_id,
                user_id=user_id,
                note=note,
            )
        )


def update_property_status(property_id: int, status: str) -> Optional[dict[str, Any]]:
    with get_property_engine().begin() as conn:
        conn.execute(
            update(properties)
            .where(properties.c.id == property_id)
            .values(status=status, updated_at=datetime.utcnow())
        )
        row = (
            conn.execute(select(properties).where(properties.c.id == property_id))
            .mappings()
            .first()
        )
    return _row_to_dict(row) if row else None


def get_deal_alerts(min_score: int = 70) -> list[dict[str, Any]]:
    deals = get_high_deals(limit=500)
    return [
        {
            "id": deal["id"],
            "address": deal["address"],
            "city": deal.get("city"),
            "state": deal.get("state"),
            "dealScore": deal.get("deal_score"),
            "estimatedValue": deal.get("estimated_value"),
            "estimatedRent": deal.get("estimated_rent"),
        }
        for deal in deals
        if (deal.get("deal_score") or 0) >= min_score
    ]
