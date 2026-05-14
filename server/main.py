"""
FastAPI backend for House Deal Scraper.
"""

import logging
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from pathlib import Path

from database import get_all_listings, init_db, upsert_listing
from server.data_sources import has_primary_listing_source, serialize_data_sources
from server.engine import ListingAnalysis, fetch_detail_page_photos, search_listings, serialize_analysis
from server.location_normalizer import normalize_location
from server.low_cost_data_engine import analyze_low_cost_property, data_priority, rent_comps
from server.property_system import (
    add_property_note,
    add_to_watchlist,
    get_deal_alerts,
    get_high_deals,
    get_property_detail,
    ingest_property,
    ingest_property_from_analysis,
    init_property_system_db,
    search_properties,
    update_property_status,
    update_property_photos,
)
from server.property_condition_analyzer import (
    PropertyAnalyzerConfigurationError,
    analyze_property_images,
    is_openai_configured,
)
from server.rent_analyzer import generate_rent_analysis, get_rent_analysis
from server.scrapers.craigslist import fetch_craigslist
from server.scrapers.facebook import fetch_facebook
from server.scrapers.realtor import fetch_realtor
from server.scrapers.redfin import fetch_redfin
from server.scrapers.rentcast import RentCastAuthenticationError, check_rentcast, fetch_rentcast
from server.scrapers.realty_mole import RealtyMoleAuthenticationError, check_realty_mole, fetch_realty_mole, is_realty_mole_enabled
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
        source_url=raw_listing.get("source_url"),
        photos=analysis.listing.photos,
    )
    serialized["listing"]["id"] = saved_listing_id
    serialized["listing"]["zip_code"] = raw_listing.get("zip_code", "")
    try:
        property_record = ingest_property_from_analysis(analysis, saved_listing_id)
        try:
            generate_rent_analysis(property_record["id"])
        except Exception as rent_exc:
            logger.warning("rent analysis generation failed for property %s: %s", property_record.get("id"), rent_exc)
        serialized["listing"]["property_intelligence_id"] = property_record.get("id")
        serialized["listing"]["property_deal_score"] = property_record.get("deal_score")
    except Exception as exc:
        logger.exception("property intelligence ingest failed: %s", exc)
        serialized["listing"]["property_intelligence_error"] = "Property intelligence ingest failed."
    return serialized


def research_item_score(item: dict) -> int:
    listing = item.get("listing") if isinstance(item, dict) else {}
    listing = listing if isinstance(listing, dict) else {}
    raw_score = (
        listing.get("property_deal_score")
        or listing.get("deal_score")
        or item.get("deal_score")
        or item.get("dealScore")
    )
    if raw_score is None:
        final_score = item.get("deal_scores", {}).get("final_score") if isinstance(item, dict) else None
        if final_score is not None:
            try:
                final_score_number = float(final_score)
                raw_score = final_score_number * 100 if final_score_number <= 1 else final_score_number
            except (TypeError, ValueError):
                raw_score = 0
    try:
        return int(round(float(raw_score or 0)))
    except (TypeError, ValueError):
        return 0


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
    max_price: Optional[float] = Query(None, ge=0, description="Maximum asking price to include"),
):
    normalized_city, normalized_state, corrected = normalize_location(city, state)
    if corrected:
        logger.info(
            "analyze location corrected from %s, %s to %s, %s",
            city, state, normalized_city, normalized_state,
        )
    try:
        results = await run_in_threadpool(search_listings, normalized_city, normalized_state, include_photos, max_price)
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
    except RentCastAuthenticationError as exc:
        logger.exception("RentCast authentication failed during analyze(%s, %s): %s", normalized_city, normalized_state, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RealtyMoleAuthenticationError as exc:
        logger.exception("Realty Mole authentication failed during analyze(%s, %s): %s", normalized_city, normalized_state, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("analyze(%s, %s) failed: %s", normalized_city, normalized_state, exc)
        raise HTTPException(status_code=500, detail="Analysis failed while fetching listings.") from exc


@app.get("/api/research")
async def api_research(
    city: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Address, county, zip, or parcel search"),
    include_photos: bool = Query(True),
    max_price: Optional[float] = Query(None, ge=0),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    mode: str = Query("both", pattern="^(database|live|both)$"),
    limit: int = Query(100, ge=1, le=500),
):
    """Unified research route used by the Research screen.

    It searches saved property intelligence and/or live sources, then returns a
    combined payload so the UI can still show research data when public live
    scrapers return zero or are blocked.
    """

    database_rows = []
    live_rows = []
    errors = []
    normalized_city = city
    normalized_state = state
    corrected = False
    live_skipped = False

    if mode in {"database", "both"}:
        try:
            database_rows = await run_in_threadpool(
                search_properties,
                city,
                state,
                q,
                max_price,
                min_score,
                limit,
            )
        except Exception as exc:
            logger.exception("research database search failed: %s", exc)
            errors.append({"source": "database", "message": str(exc)})

    if mode in {"live", "both"}:
        if not city or not state:
            live_skipped = True
            errors.append({"source": "live", "message": "City and state are required for live research."})
        else:
            normalized_city, normalized_state, corrected = normalize_location(city, state)
            try:
                results = await run_in_threadpool(search_listings, normalized_city, normalized_state, include_photos, max_price)
                live_rows = [persist_analysis(result) for result in results]
                if min_score is not None:
                    live_rows = [item for item in live_rows if research_item_score(item) >= min_score]
                if corrected:
                    for item in live_rows:
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
            except (RentCastAuthenticationError, RealtyMoleAuthenticationError) as exc:
                logger.exception("research live source authentication failed: %s", exc)
                errors.append({"source": "live", "message": str(exc)})
            except Exception as exc:
                logger.exception("research live analysis failed: %s", exc)
                errors.append({"source": "live", "message": "Live research failed while fetching listings."})

    combined = []
    seen = set()
    for item in [*database_rows, *live_rows]:
        listing = item.get("listing") if isinstance(item, dict) else None
        row = listing if isinstance(listing, dict) else item
        key = (
            str(row.get("address") or "").lower(),
            str(row.get("city") or "").lower(),
            str(row.get("state") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        combined.append(item)

    return {
        "success": True,
        "mode": mode,
        "city": normalized_city,
        "state": normalized_state,
        "corrected": corrected,
        "database": {
            "count": len(database_rows),
            "data": database_rows,
        },
        "live": {
            "count": len(live_rows),
            "data": live_rows,
            "skipped": live_skipped,
        },
        "combined_count": len(combined),
        "data": combined,
        "errors": errors,
    }


@app.get("/")
async def root():
    return FileResponse(UI_INDEX)


@app.get("/dashboard")
@app.get("/research")
@app.get("/database")
@app.get("/ai")
@app.get("/maps")
@app.get("/alerts")
@app.get("/crm")
@app.get("/settings")
async def app_page():
    return FileResponse(UI_INDEX)


@app.get("/status")
async def status():
    return {"status": "House Deal Scraper Backend Running"}


@app.get("/data-sources")
async def data_sources():
    sources = serialize_data_sources()
    rentcast_status = check_rentcast()
    realty_mole_status = check_realty_mole()
    return {
        "primary_ready": has_primary_listing_source(),
        "ai_analyzer_ready": is_openai_configured(),
        "live_check": {
            "rentcast": rentcast_status,
            "realty_mole": realty_mole_status,
        },
        "sources": sources,
        "required_setup": [
            source
            for source in sources
            if source["required_for_analysis"] and not source["enabled"]
        ],
    }


@app.post("/api/analyze-property")
async def api_analyze_property(
    images: list[UploadFile] = File(...),
    address: str = Form(""),
    city: str = Form(""),
    state: str = Form(""),
    asking_price: Optional[float] = Form(None),
    rent_estimate: Optional[float] = Form(None),
    arv_estimate: Optional[float] = Form(None),
):
    try:
        image_payload = []
        for image in images[:20]:
            image_payload.append((image.filename or "property.jpg", image.content_type or "image/jpeg", await image.read()))
        return await run_in_threadpool(
            analyze_property_images,
            image_payload,
            address,
            city,
            state,
            asking_price,
            rent_estimate,
            arv_estimate,
        )
    except PropertyAnalyzerConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("property condition analysis failed: %s", exc)
        raise HTTPException(status_code=500, detail="Property condition analysis failed.") from exc


@app.get("/debug/live-data")
async def debug_live_data(
    city: str = Query("Detroit", description="City to test"),
    state: str = Query("MI", description="State to test"),
):
    normalized_city, normalized_state, corrected = normalize_location(city, state)
    rentcast_status = check_rentcast(normalized_city, normalized_state)
    realty_mole_status = check_realty_mole(normalized_city, normalized_state)
    return {
        "city": normalized_city,
        "state": normalized_state,
        "corrected": corrected,
        "requested_city": city,
        "requested_state": state,
        "primary_ready": has_primary_listing_source(),
        "rentcast": rentcast_status,
        "realty_mole": realty_mole_status,
    }


@app.post("/api/property/analyze")
async def api_low_cost_property_analyze(data: dict):
    return await run_in_threadpool(analyze_low_cost_property, data)


@app.post("/api/rent-comps")
async def api_rent_comps(data: dict):
    city = str(data.get("city") or "")
    state = str(data.get("state") or "NY")
    bedrooms = data.get("bedrooms")
    return await run_in_threadpool(rent_comps, city, state, bedrooms)


@app.get("/api/data-priority")
async def api_data_priority():
    return data_priority()


@app.post("/api/properties/ingest")
async def api_ingest_property(data: dict):
    try:
        property_record = await run_in_threadpool(ingest_property, data)
        try:
            await run_in_threadpool(generate_rent_analysis, property_record["id"])
        except Exception as rent_exc:
            logger.warning("rent analysis generation failed for property %s: %s", property_record.get("id"), rent_exc)
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


@app.get("/api/properties/search")
async def api_search_properties(
    city: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Address, county, zip, or parcel search"),
    max_price: Optional[float] = Query(None, ge=0),
    min_score: Optional[int] = Query(None, ge=0, le=100),
    limit: int = Query(100, ge=1, le=500),
):
    try:
        rows = await run_in_threadpool(
            search_properties,
            city,
            state,
            q,
            max_price,
            min_score,
            limit,
        )
        return {
            "success": True,
            "count": len(rows),
            "data": rows,
        }
    except Exception as exc:
        logger.exception("property search failed: %s", exc)
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


@app.get("/api/properties/{property_id}/rent-analysis")
async def api_get_rent_analysis(property_id: int):
    try:
        result = await run_in_threadpool(get_rent_analysis, property_id)
        return {
            "success": True,
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("rent analysis lookup failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/properties/{property_id}/rent-analysis/refresh")
async def api_refresh_rent_analysis(property_id: int):
    try:
        result = await run_in_threadpool(generate_rent_analysis, property_id)
        return {
            "success": True,
            **result,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("rent analysis refresh failed: %s", exc)
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


@app.post("/api/properties/{property_id}/refresh-photos")
async def api_refresh_property_photos(property_id: int):
    try:
        detail = await run_in_threadpool(get_property_detail, property_id)
        property_record = detail.get("property")
        if not property_record:
            raise HTTPException(status_code=404, detail="Property not found")
        source_url = property_record.get("source_url") or (property_record.get("links") or {}).get("source")
        if not source_url:
            raise HTTPException(status_code=400, detail="Property does not have a source URL to scrape for photos.")
        photos = await run_in_threadpool(fetch_detail_page_photos, source_url, 20)
        if not photos:
            raise HTTPException(status_code=404, detail="No photos were found on the saved source page.")
        property_record = await run_in_threadpool(update_property_photos, property_id, photos)
        return {
            "success": True,
            "photos": photos,
            "property": property_record,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("property photo refresh failed: %s", exc)
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
    scrapers = []
    if is_realty_mole_enabled():
        scrapers.append(("Realty Mole", fetch_realty_mole))
    scrapers.extend([
        ("RentCast", fetch_rentcast),
        ("Redfin", fetch_redfin),
        ("Zillow", fetch_zillow),
        ("Realtor", fetch_realtor),
        ("Craigslist", fetch_craigslist),
        ("Facebook", fetch_facebook),
    ])
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
