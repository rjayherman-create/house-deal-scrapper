"""
FastAPI backend for House Deal Scraper.
This file exposes API endpoints that call engine.py for:
- Listing aggregation
- AI analysis
- Comp scoring
- System ratings
- Questionnaire generation
"""

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from server.engine import search_listings, serialize_analysis


app = FastAPI(
    title="House Deal Scraper API",
    description="Backend for property analysis, AI scoring, and questionnaire generation.",
    version="1.0.0"
)

# Allow GUI, Railway, localhost, etc.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Health Check
# ---------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "message": "Backend running"}


# ---------------------------------------------------------
# Main Analysis Endpoint (ASYNC)
# ---------------------------------------------------------

@app.get("/analyze")
async def analyze(
    city: str = Query(..., description="City to search"),
    state: str = Query(..., description="State to search"),
    include_photos: bool = Query(False, description="Fetch photos from all sources")
):
    """
    Main endpoint:
    - Scrapes Redfin, Zillow, Realtor, Craigslist, Facebook
    - Runs AI analysis (photo age, distress, systems)
    - Computes comp score + deal score
    - Generates buyer questionnaire + checklist
    """
    try:
        results = await search_listings(city, state, include_photos=include_photos)
        return [serialize_analysis(r) for r in results]

    except Exception as e:
        return {
            "error": True,
            "message": str(e)
        }


# ---------------------------------------------------------
# Root
# ---------------------------------------------------------

@app.get("/")
async def root():
    return {"status": "House Deal Scraper Backend Running"}
