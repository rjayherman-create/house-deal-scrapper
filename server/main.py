"""
FastAPI backend for House Deal Scraper.
"""

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from pathlib import Path

from database import get_all_listings, init_db, upsert_listing
from server.data_sources import has_primary_listing_source, serialize_data_sources
from server.engine import ListingAnalysis, search_listings, serialize_analysis
from server.location_normalizer import normalize_location
from server.property_system import (
    add_property_note,
    add_to_watchlist,
    get_deal_alerts,
    get_high_deals,
    get_property_detail,
    ingest_property,
    ingest_property_from_analysis,
    init_property_system_db,
    update_property_status,
)
from server.scrapers.craigslist import fetch_craigslist
from server.scrapers.facebook import fetch_facebook
from server.scrapers.realtor import fetch_realtor
from server.scrapers.redfin import fetch_redfin
from server.scrapers.rentcast import check_rentcast, fetch_rentcast
from server.scrapers.zillow import fetch_zillow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="House Deal Scraper API",
    description="Backend for property analysis, saved listings, and questionnaire generation.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
UI_INDEX = STATIC_DIR / "index.html"


@app.on_event("startup")
def startup() -> None:
    init_db()
    init_property_system_db()


def persist_analysis(analysis: ListingAnalysis) -> dict:
    serialized = serialize_analysis(analysis)
    raw_listing = analysis.listing.raw_data or {}
    saved_listing_id = upsert_listing(
        address=analysis.listing.address,
        city=analysis.listing.city,
        state=analysis.listing.state,
        zip_code=raw_listing.get("zip_code"),
        source=analysis.listing.source,
        asking_price=analysis.listing.price,
    )
    serialized["listing"]["id"] = saved_listing_id
    serialized["listing"]["zip_code"] = raw_listing.get("zip_code", "")
    try:
        property_record = ingest_property_from_analysis(analysis, saved_listing_id)
        serialized["listing"]["property_intelligence_id"] = property_record.get("id")
        serialized["listing"]["property_deal_score"] = property_record.get("deal_score")
    except Exception as exc:
        logger.exception("property intelligence ingest failed: %s", exc)
        serialized["listing"]["property_intelligence_error"] = "Property intelligence ingest failed."
    return serialized


@app.get("/health")
async def health():
    return {"status": "ok", "message": "Backend running"}


@app.get("/listings")
async def listings(
    city: Optional[str] = Query(None, description="Optional city filter"),
    state: Optional[str] = Query(None, description="Optional state filter"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of saved listings"),
):
    return {"listings": get_all_listings(city=city, state=state, limit=limit)}


@app.get("/analyze")
async def analyze(
    city: str = Query(..., description="City to search"),
    state: str = Query(..., description="State to search"),
    include_photos: bool = Query(False, description="Fetch photos from all sources"),
):
    normalized_city, normalized_state, corrected = normalize_location(city, state)
    if corrected:
        logger.info(
            "analyze location corrected from %s, %s to %s, %s",
            city, state, normalized_city, normalized_state,
        )
    try:
        results = await run_in_threadpool(search_listings, normalized_city, normalized_state, include_photos)
        logger.info(
            "analyze(%s, %s): %d listings returned",
            normalized_city, normalized_state, len(results),
        )
        serialized_results = [persist_analysis(result) for result in results]
        if corrected:
            for item in serialized_results:
                item.setdefault("search", {})
                item["search"].update(
                    {
                        "requested_city": city,
                        "requested_state": state,
                        "city": normalized_city,
                        "state": normalized_state,
                        "corrected": True,
                    }
                )
        return serialized_results
    except Exception as exc:
        logger.exception("analyze(%s, %s) failed: %s", normalized_city, normalized_state, exc)
        raise HTTPException(status_code=500, detail="Analysis failed while fetching listings.") from exc


@app.get("/")
async def root():
    return FileResponse(UI_INDEX)


@app.get("/status")
async def status():
    return {"status": "House Deal Scraper Backend Running"}


@app.get("/data-sources")
async def data_sources():
    sources = serialize_data_sources()
    rentcast_status = await run_in_threadpool(check_rentcast)
    return {
        "primary_ready": has_primary_listing_source(),
        "live_check": {
            "rentcast": rentcast_status,
        },
        "sources": sources,
        "required_setup": [
            source
            for source in sources
            if source["required_for_analysis"] and not source["enabled"]
        ],
    }


@app.get("/debug/live-data")
async def debug_live_data(
    city: str = Query("Detroit", description="City to test"),
    state: str = Query("MI", description="State to test"),
):
    normalized_city, normalized_state, corrected = normalize_location(city, state)
    rentcast_status = await run_in_threadpool(check_rentcast, normalized_city, normalized_state)
    return {
        "city": normalized_city,
        "state": normalized_state,
        "corrected": corrected,
        "requested_city": city,
        "requested_state": state,
        "primary_ready": has_primary_listing_source(),
        "rentcast": rentcast_status,
    }


@app.post("/api/properties/ingest")
async def api_ingest_property(data: dict):
    try:
        property_record = await run_in_threadpool(ingest_property, data)
        return {
            "success": True,
            "property": property_record,
        }
    except Exception as exc:
        logger.exception("property ingest failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/properties/high-deals")
async def api_high_deals(limit: int = Query(100, ge=1, le=500)):
    try:
        rows = await run_in_threadpool(get_high_deals, limit)
        return {
            "success": True,
            "count": len(rows),
            "data": rows,
        }
    except Exception as exc:
        logger.exception("high deals lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/properties/{property_id}")
async def api_property_detail(property_id: int):
    try:
        detail = await run_in_threadpool(get_property_detail, property_id)
        if not detail["property"]:
            raise HTTPException(status_code=404, detail="Property not found")
        return {
            "success": True,
            **detail,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("property detail lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/watchlist/add")
async def api_add_watchlist(data: dict):
    try:
        property_id = int(data.get("propertyId") or data.get("property_id"))
        user_id = str(data.get("userId") or data.get("user_id") or "")
        if not user_id:
            raise ValueError("userId is required")
        await run_in_threadpool(add_to_watchlist, property_id, user_id)
        return {
            "success": True,
            "message": "Added to watchlist",
        }
    except Exception as exc:
        logger.exception("watchlist add failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/properties/note")
async def api_add_property_note(data: dict):
    try:
        property_id = int(data.get("propertyId") or data.get("property_id"))
        user_id = data.get("userId") or data.get("user_id")
        note = str(data.get("note") or "")
        if not note:
            raise ValueError("note is required")
        await run_in_threadpool(add_property_note, property_id, user_id, note)
        return {
            "success": True,
            "message": "Note added",
        }
    except Exception as exc:
        logger.exception("property note add failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/properties/{property_id}/status")
async def api_update_property_status(property_id: int, data: dict):
    try:
        status_value = str(data.get("status") or "").strip().upper()
        if not status_value:
            raise ValueError("status is required")
        property_record = await run_in_threadpool(update_property_status, property_id, status_value)
        if not property_record:
            raise HTTPException(status_code=404, detail="Property not found")
        return {
            "success": True,
            "property": property_record,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("property status update failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/deals/alerts")
async def api_deal_alerts(min_score: int = Query(70, ge=0, le=100)):
    try:
        alerts = await run_in_threadpool(get_deal_alerts, min_score)
        return {
            "success": True,
            "alerts": alerts,
        }
    except Exception as exc:
        logger.exception("deal alerts lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/debug/scrapers")
async def debug_scrapers(
    city: str = Query("Detroit", description="City to test"),
    state: str = Query("MI", description="State to test"),
):
    normalized_city, normalized_state, corrected = normalize_location(city, state)
    scrapers = [
        ("RentCast", fetch_rentcast),
        ("Redfin", fetch_redfin),
        ("Zillow", fetch_zillow),
        ("Realtor", fetch_realtor),
        ("Craigslist", fetch_craigslist),
        ("Facebook", fetch_facebook),
    ]
    results = []
    for name, scraper in scrapers:
        try:
            rows = await run_in_threadpool(scraper, normalized_city, normalized_state, 5)
            results.append({
                "source": name,
                "ok": True,
                "count": len(rows),
                "sample": rows[:1],
            })
        except Exception as exc:
            results.append({
                "source": name,
                "ok": False,
                "count": 0,
                "error": str(exc),
            })
    return {
        "city": normalized_city,
        "state": normalized_state,
        "corrected": corrected,
        "requested_city": city,
        "requested_state": state,
        "sources": serialize_data_sources(),
        "scrapers": results,
    }
