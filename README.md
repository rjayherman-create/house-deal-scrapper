house-deal-scraper

## Required production data source

Set this in Railway so the analyzer has reliable live listing and valuation data:

```env
RENTCAST_API_KEY=your_rentcast_key
RENTCAST_API_BASE_URL=https://api.rentcast.io/v1
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB
DISTRESSIQ_DB_PATH=/tmp/distressiq.db
OPENAI_API_KEY=your_openai_key
OPENAI_VISION_MODEL=gpt-4.1-mini
```

The app still keeps Redfin, Realtor, Craigslist, Zillow, and Facebook as best-effort fallback scrapers, but those sources can return zero results from hosted servers because they are HTML pages with changing markup and anti-bot controls.

`DATABASE_URL` enables the persistent property intelligence system on Railway. The app creates missing `properties`, `property_snapshots`, `watchlists`, and `property_notes` tables without dropping or recreating existing data.

Useful production diagnostics:

- `/data-sources` shows configured and missing data sources.
- `/debug/live-data?city=Detroit&state=MI` tests the primary live API and explains missing key/auth/quota/zero-result issues.
- `/debug/scrapers?city=Detroit&state=MI` tests each source and returns counts.
- `/analyze?city=Detroit&state=MI&max_price=150000&include_photos=true` runs the full analysis pipeline with optional price filtering and photos.
- `/api/properties/high-deals` returns saved properties ordered by deal score.
- `/api/deals/alerts` returns saved properties with deal scores at or above 70.
- `/api/properties/{property_id}/status` updates a saved property's pipeline status.
- `/api/analyze-property` accepts property photo uploads and returns AI condition, rehab, ARV, rent, flip, rental, and Section 8 analysis.
