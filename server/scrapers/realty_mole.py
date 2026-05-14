import logging
import os
from typing import Any, Dict, List, Optional

import requests


logger = logging.getLogger(__name__)

REALTY_MOLE_BASE_URL = os.getenv(
    "REALTY_MOLE_API_BASE_URL",
    "https://realty-mole-property-api.p.rapidapi.com",
).rstrip("/")
REALTY_MOLE_HOST = os.getenv("REALTY_MOLE_RAPIDAPI_HOST", "realty-mole-property-api.p.rapidapi.com")


class RealtyMoleAuthenticationError(RuntimeError):
    pass


def realty_mole_api_key() -> str:
    return (
        os.getenv("REALTY_MOLE_API_KEY")
        or os.getenv("RAPIDAPI_KEY")
        or ""
    ).strip()


def is_realty_mole_enabled() -> bool:
    return bool(realty_mole_api_key())


def _number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", []):
            return value
    return None


def _address(item: Dict[str, Any], city: str, state: str) -> str:
    return _first(
        item.get("formattedAddress"),
        item.get("address"),
        item.get("addressLine1"),
        ", ".join(
            part
            for part in [
                item.get("addressLine1"),
                item.get("city") or city,
                item.get("state") or state,
                item.get("zipCode"),
            ]
            if part
        ),
    ) or ""


def _photos(item: Dict[str, Any]) -> List[str]:
    values = _first(
        item.get("photos"),
        item.get("images"),
        item.get("imageUrls"),
        item.get("photoUrls"),
        item.get("thumbnail"),
        [],
    )
    if isinstance(values, str):
        return [values] if values.startswith("http") else []
    if not isinstance(values, list):
        return []
    photos: List[str] = []
    for photo in values[:12]:
        if isinstance(photo, str) and photo.startswith("http"):
            photos.append(photo)
        elif isinstance(photo, dict):
            url = _first(photo.get("url"), photo.get("href"), photo.get("src"))
            if isinstance(url, str) and url.startswith("http"):
                photos.append(url)
    return photos


def _source_url(item: Dict[str, Any], address: str) -> str:
    explicit = _first(item.get("url"), item.get("listingUrl"), item.get("sourceUrl"))
    if explicit:
        return str(explicit)
    if address:
        from urllib.parse import quote_plus

        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(address)}"
    return ""


def _request(path: str, params: Dict[str, Any]) -> Any:
    api_key = realty_mole_api_key()
    if not api_key:
        return []
    response = requests.get(
        f"{REALTY_MOLE_BASE_URL}{path}",
        params={k: v for k, v in params.items() if v not in (None, "")},
        headers={
            "Accept": "application/json",
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": REALTY_MOLE_HOST,
            "User-Agent": "HouseDealScraper/1.0",
        },
        timeout=20,
    )
    if response.status_code in (401, 403):
        raise RealtyMoleAuthenticationError("Realty Mole authentication failed. Check REALTY_MOLE_API_KEY or RAPIDAPI_KEY in Railway.")
    response.raise_for_status()
    return response.json()


def _payload_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("listings") or payload.get("results") or []
        return [row for row in rows if isinstance(row, dict)]
    return []


def check_realty_mole(city: str = "Detroit", state: str = "MI") -> Dict[str, Any]:
    if not is_realty_mole_enabled():
        return {
            "enabled": False,
            "ok": False,
            "status": "missing_api_key",
            "message": "REALTY_MOLE_API_KEY or RAPIDAPI_KEY is not set.",
            "base_url": REALTY_MOLE_BASE_URL,
        }
    try:
        payload = _request("/saleListings", {"city": city, "state": state.upper(), "limit": 3})
        rows = _payload_rows(payload)
        return {
            "enabled": True,
            "ok": True,
            "status": "ready" if rows else "connected_zero_results",
            "message": f"Realty Mole returned {len(rows)} live sale listing(s) for {city}, {state.upper()}.",
            "base_url": REALTY_MOLE_BASE_URL,
            "sample_count": len(rows),
        }
    except RealtyMoleAuthenticationError as exc:
        return {
            "enabled": True,
            "ok": False,
            "status": "auth_failed",
            "message": str(exc),
            "base_url": REALTY_MOLE_BASE_URL,
        }
    except requests.HTTPError as exc:
        return {
            "enabled": True,
            "ok": False,
            "status": "http_error",
            "status_code": exc.response.status_code if exc.response is not None else None,
            "message": exc.response.text[:500] if exc.response is not None else str(exc),
            "base_url": REALTY_MOLE_BASE_URL,
        }
    except requests.RequestException as exc:
        return {
            "enabled": True,
            "ok": False,
            "status": "network_error",
            "message": str(exc),
            "base_url": REALTY_MOLE_BASE_URL,
        }


def fetch_realty_mole(city: str, state: str, limit: int = 20) -> List[Dict[str, Any]]:
    if not is_realty_mole_enabled():
        logger.info("Realty Mole: no API key configured")
        return []

    try:
        payload = _request("/saleListings", {"city": city, "state": state.upper(), "limit": limit})
    except RealtyMoleAuthenticationError:
        raise
    except Exception as exc:
        logger.warning("Realty Mole saleListings lookup failed for %s, %s: %s", city, state, exc)
        return []

    listings = []
    for item in _payload_rows(payload)[:limit]:
        address = _address(item, city, state.upper())
        price = _number(_first(item.get("price"), item.get("listPrice"), item.get("askingPrice")))
        if not address or not price:
            continue
        listings.append(
            {
                "address": address,
                "city": item.get("city") or city,
                "state": item.get("state") or state.upper(),
                "zip_code": item.get("zipCode") or item.get("zipcode") or "",
                "asking_price": price,
                "beds": _number(item.get("bedrooms")),
                "baths": _number(item.get("bathrooms")),
                "sqft": _number(item.get("squareFootage")),
                "year_built": item.get("yearBuilt"),
                "property_type": item.get("propertyType"),
                "lot_size": _number(item.get("lotSize")),
                "source_url": _source_url(item, address),
                "photos": _photos(item),
                "source_id": item.get("id") or item.get("propertyId") or address,
                "raw_data": item,
            }
        )

    logger.info("Realty Mole: normalized %d live listing(s) for %s, %s", len(listings), city, state.upper())
    return listings
