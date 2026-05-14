import csv
import io
import json
import logging
import re
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


def _extract_digits(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^\d.]", "", str(value))


def _get_redfin_region(city: str, state: str, headers: dict) -> Optional[tuple]:
    """
    Look up the Redfin region_id and region_type for a city/state pair via
    their autocomplete endpoint.  Returns (region_id, region_type) or None.
    """
    try:
        resp = requests.get(
            "https://www.redfin.com/stingray/do/location-autocomplete",
            params={"location": f"{city} {state}", "v": 2},
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        # Response is prefixed with "{}&&" to prevent JSONP hijacking
        text = resp.text
        if "&&" in text:
            text = text.split("&&", 1)[1]

        data = json.loads(text)
        payload = data.get("payload", {})

        def _parse_region_id(id_str: str):
            parts = id_str.split("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return parts[1], int(parts[0])
            return None

        # Prefer exact match
        exact = payload.get("exactMatch")
        if exact:
            result = _parse_region_id(exact.get("id", ""))
            if result:
                return result

        # Fall back to first suggestion in any section
        for section in payload.get("sections", []):
            for row in section.get("rows", []):
                result = _parse_region_id(row.get("id", ""))
                if result:
                    return result

    except Exception as exc:
        logger.warning("Redfin region lookup failed for %s, %s: %s", city, state, exc)

    return None


def fetch_redfin(city, state, limit):
    """
    Redfin CSV API scraper.

    First resolves the city/state to a Redfin region_id via the autocomplete
    endpoint, then downloads the GIS CSV export for that region.
    Returns normalized listing dicts.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Referer": "https://www.redfin.com/",
        "Accept-Language": "en-US,en;q=0.9",
    }

    region = _get_redfin_region(city, state, headers)
    if not region:
        logger.warning("Redfin: could not resolve region for %s, %s", city, state)
        return []

    region_id, region_type = region

    try:
        resp = requests.get(
            "https://www.redfin.com/stingray/api/gis-csv",
            params={
                "al": 1,
                "num_homes": limit,
                "region_id": region_id,
                "region_type": region_type,
                "status": 1,
                "uipt": "1,2,3,4,5,6,7",
                "v": 8,
            },
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(
                "Redfin CSV returned HTTP %s for region %s/%s",
                resp.status_code, region_id, region_type,
            )
            return []

        reader = csv.DictReader(io.StringIO(resp.text))
        results = []

        for row in reader:
            address = row.get("ADDRESS") or row.get("Street Line")
            price = row.get("PRICE") or row.get("Price")
            if not address or not price:
                continue

            asking_price = _extract_digits(price)
            if not asking_price:
                continue

            results.append({
                "address": address.strip(),
                "city": row.get("CITY") or city,
                "state": row.get("STATE OR PROVINCE") or state,
                "zip_code": row.get("ZIP OR POSTAL CODE", ""),
                "asking_price": asking_price,
            })
            if len(results) >= limit:
                break

        logger.info("Redfin: fetched %d listings for %s, %s", len(results), city, state)
        return results

    except Exception as exc:
        logger.warning("Redfin CSV fetch failed for %s, %s: %s", city, state, exc)
        return []
