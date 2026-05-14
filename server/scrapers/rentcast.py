import os
from typing import Any, Dict, List, Optional

import requests


RENTCAST_BASE_URL = os.getenv("RENTCAST_API_BASE_URL", "https://api.rentcast.io/v1").rstrip("/")


def is_rentcast_enabled() -> bool:
    return bool(os.getenv("RENTCAST_API_KEY"))


def _request(path: str, params: Dict[str, Any]) -> Any:
    api_key = os.getenv("RENTCAST_API_KEY")
    if not api_key:
        return None

    response = requests.get(
        f"{RENTCAST_BASE_URL}{path}",
        params={k: v for k, v in params.items() if v not in (None, "")},
        headers={
            "Accept": "application/json",
            "X-Api-Key": api_key,
            "User-Agent": "HouseDealScraper/1.0",
        },
        timeout=15,
    )
    if response.status_code in (401, 403):
        raise RuntimeError("RentCast authentication failed. Check RENTCAST_API_KEY in Railway.")
    response.raise_for_status()
    return response.json()


def check_rentcast(city: str = "Detroit", state: str = "MI") -> Dict[str, Any]:
    api_key = os.getenv("RENTCAST_API_KEY")
    if not api_key:
        return {
            "enabled": False,
            "ok": False,
            "status": "missing_api_key",
            "message": "RENTCAST_API_KEY is not set in Railway.",
            "base_url": RENTCAST_BASE_URL,
        }

    try:
        payload = _request(
            "/listings/sale",
            {
                "city": city,
                "state": state.upper(),
                "status": "Active",
                "limit": 3,
            },
        )
        rows = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
        return {
            "enabled": True,
            "ok": True,
            "status": "ready" if rows else "connected_zero_results",
            "message": (
                f"RentCast returned {len(rows)} active sale listing(s) for {city}, {state.upper()}."
                if rows
                else f"RentCast connected, but returned zero active sale listings for {city}, {state.upper()}."
            ),
            "base_url": RENTCAST_BASE_URL,
            "sample_count": len(rows),
        }
    except RuntimeError as exc:
        return {
            "enabled": True,
            "ok": False,
            "status": "auth_failed",
            "message": str(exc),
            "base_url": RENTCAST_BASE_URL,
        }
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        response_text = exc.response.text[:500] if exc.response is not None else ""
        return {
            "enabled": True,
            "ok": False,
            "status": "http_error",
            "status_code": status_code,
            "message": response_text or str(exc),
            "base_url": RENTCAST_BASE_URL,
        }
    except requests.RequestException as exc:
        return {
            "enabled": True,
            "ok": False,
            "status": "network_error",
            "message": str(exc),
            "base_url": RENTCAST_BASE_URL,
        }


def _number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _format_address(item: Dict[str, Any], fallback_city: str, fallback_state: str) -> str:
    return _first(
        item.get("formattedAddress"),
        item.get("address"),
        ", ".join(
            part
            for part in [
                item.get("addressLine1"),
                item.get("city") or fallback_city,
                item.get("state") or fallback_state,
                item.get("zipCode"),
            ]
            if part
        ),
    ) or ""


def _normalize_sale_listing(item: Dict[str, Any], city: str, state: str) -> Dict[str, Any]:
    price = _number(
        _first(
            item.get("price"),
            item.get("listPrice"),
            item.get("askingPrice"),
            item.get("lastSalePrice"),
        )
    )
    return {
        "address": _format_address(item, city, state),
        "city": item.get("city") or city,
        "state": item.get("state") or state,
        "zip_code": item.get("zipCode") or item.get("zipcode") or "",
        "asking_price": price,
        "beds": _number(item.get("bedrooms")),
        "baths": _number(item.get("bathrooms")),
        "sqft": _number(item.get("squareFootage")),
        "year_built": item.get("yearBuilt"),
        "property_type": item.get("propertyType"),
        "lot_size": item.get("lotSize"),
        "source_url": item.get("url") or item.get("listingUrl"),
        "source_id": item.get("id") or item.get("propertyId"),
        "raw_data": item,
    }


def fetch_rentcast(city: str, state: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Primary production source for live sale listings.

    RentCast returns active sale listings by city/state, plus normalized fields
    that the analysis engine can score without brittle HTML scraping.
    """
    if not is_rentcast_enabled():
        return []

    payload = _request(
        "/listings/sale",
        {
            "city": city,
            "state": state.upper(),
            "status": "Active",
            "limit": limit,
        },
    )
    rows = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []

    listings = []
    for item in rows[:limit]:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_sale_listing(item, city, state.upper())
        if normalized["address"] and normalized["asking_price"]:
            listings.append(normalized)
    return listings


def fetch_value_estimate(address: str, comp_count: int = 10) -> Dict[str, Any]:
    if not is_rentcast_enabled() or not address:
        return {}
    payload = _request(
        "/avm/value",
        {
            "address": address,
            "compCount": max(5, min(25, comp_count)),
            "lookupSubjectAttributes": "true",
        },
    )
    return payload if isinstance(payload, dict) else {}


def fetch_rent_estimate(address: str, comp_count: int = 10) -> Dict[str, Any]:
    if not is_rentcast_enabled() or not address:
        return {}
    payload = _request(
        "/avm/rent/long-term",
        {
            "address": address,
            "compCount": max(5, min(25, comp_count)),
            "lookupSubjectAttributes": "true",
        },
    )
    return payload if isinstance(payload, dict) else {}


def fetch_property_record(address: str) -> Dict[str, Any]:
    if not is_rentcast_enabled() or not address:
        return {}
    payload = _request("/properties", {"address": address, "limit": 1})
    if isinstance(payload, list):
        return payload[0] if payload else {}
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data[0] if data else {}
        return payload
    return {}
