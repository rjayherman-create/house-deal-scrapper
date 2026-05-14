"""HUD Fair Market Rent lookup helpers.

The app should not fabricate Section 8 or FMR values. This module only returns
data when a HUD USER API token is configured and the HUD endpoint returns a
matching record. Callers must treat ``None`` as realtime data unavailable.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

HUD_BASE_URL = os.getenv("HUD_FMR_BASE_URL", "https://www.huduser.gov/hudapi/public/fmr")


def _token() -> str:
    return (os.getenv("HUD_USER_TOKEN") or os.getenv("HUD_API_TOKEN") or "").strip()


def is_hud_fmr_enabled() -> bool:
    return bool(_token())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/json",
        "User-Agent": "HouseDealScraper/1.0",
    }


def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _bedroom_keys(bedrooms: int) -> list[str]:
    bedroom_count = max(0, min(int(bedrooms or 2), 4))
    labels = {
        0: ["efficiency", "efficiency_fmr", "fmr_0", "zero_bedroom", "0br"],
        1: ["one_bedroom", "onebr", "fmr_1", "1br", "bedroom_1"],
        2: ["two_bedroom", "twobr", "fmr_2", "2br", "bedroom_2"],
        3: ["three_bedroom", "threebr", "fmr_3", "3br", "bedroom_3"],
        4: ["four_bedroom", "fourbr", "fmr_4", "4br", "bedroom_4"],
    }
    return labels[bedroom_count]


def _walk_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    records: list[dict[str, Any]] = []
    for key in ("data", "results", "fmr", "areas", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            records.append(value)
    if not records:
        records.append(payload)
    return records


def _matches(record: dict[str, Any], county: Optional[str], zip_code: Optional[str]) -> bool:
    if zip_code:
        haystack = " ".join(str(record.get(key) or "") for key in ("zip_code", "zip", "zipCode", "fips"))
        if str(zip_code) in haystack:
            return True
    if county:
        county_norm = county.lower().replace(" county", "").strip()
        haystack = " ".join(
            str(record.get(key) or "")
            for key in ("county", "county_name", "area_name", "metro_name", "name")
        ).lower()
        if county_norm and county_norm in haystack:
            return True
    return not county and not zip_code


def _rent_from_record(record: dict[str, Any], bedrooms: int) -> Optional[float]:
    normalized = {str(key).lower().replace("-", "_").replace(" ", "_"): value for key, value in record.items()}
    for key in _bedroom_keys(bedrooms):
        value = _num(normalized.get(key))
        if value:
            return value
    for key, value in normalized.items():
        if str(bedrooms) in key and ("rent" in key or "fmr" in key or "br" in key):
            parsed = _num(value)
            if parsed:
                return parsed
    return None


@lru_cache(maxsize=512)
def _fetch_state_payload(state: str) -> Optional[Any]:
    if not is_hud_fmr_enabled():
        return None
    state_code = (state or "").strip().upper()
    if not state_code:
        return None
    url = f"{HUD_BASE_URL.rstrip('/')}/data/{state_code}"
    try:
        response = requests.get(url, headers=_headers(), timeout=15)
    except requests.RequestException as exc:
        logger.warning("HUD FMR lookup failed for %s: %s", state_code, exc)
        return None
    if response.status_code in {401, 403}:
        logger.warning("HUD FMR authentication failed. Check HUD_USER_TOKEN in Railway.")
        return None
    if response.status_code != 200:
        logger.warning("HUD FMR lookup returned HTTP %s for %s", response.status_code, state_code)
        return None
    try:
        return response.json()
    except ValueError:
        logger.warning("HUD FMR lookup returned non-JSON response for %s", state_code)
        return None


def lookup_hud_fmr(
    state: str,
    county: Optional[str] = None,
    zip_code: Optional[str] = None,
    bedrooms: int = 2,
) -> Optional[dict[str, Any]]:
    payload = _fetch_state_payload(state)
    if payload is None:
        return None
    for record in _walk_records(payload):
        if not _matches(record, county, zip_code):
            continue
        rent = _rent_from_record(record, bedrooms)
        if not rent:
            continue
        return {
            "rent": rent,
            "bedrooms": bedrooms,
            "source": "HUD USER FMR API",
            "source_url": HUD_BASE_URL,
            "raw": record,
        }
    return None
