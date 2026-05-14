"""Normalize user-entered city/state values before scraper calls."""

from __future__ import annotations

import re


COMMON_CITY_FIXES: dict[tuple[str, str], str] = {
    ("detriot", "mi"): "Detroit",
    ("detoit", "mi"): "Detroit",
    ("detroir", "mi"): "Detroit",
}


def normalize_location(city: str, state: str) -> tuple[str, str, bool]:
    clean_city = re.sub(r"\s+", " ", (city or "").strip())
    clean_state = (state or "").strip().upper()
    key = (clean_city.lower(), clean_state.lower())
    corrected_city = COMMON_CITY_FIXES.get(key)
    if corrected_city:
        return corrected_city, clean_state, True
    return clean_city.title(), clean_state, False
