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
from server.engine import ListingAnalysis, search_listings, serialize_analysis

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
    try:
        results = await run_in_threadpool(search_listings, city, state, include_photos)
        logger.info("analyze(%s, %s): %d listings returned", city, state, len(results))
        return [persist_analysis(result) for result in results]
    except Exception as exc:
        logger.exception("analyze(%s, %s) failed: %s", city, state, exc)
        raise HTTPException(status_code=500, detail="Analysis failed while fetching listings.") from exc


@app.get("/")
async def root():
    return FileResponse(UI_INDEX)


@app.get("/status")
async def status():
    return {"status": "House Deal Scraper Backend Running"}
