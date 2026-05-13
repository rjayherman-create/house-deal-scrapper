import json
import re
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup


def _clean_price(value: Any) -> str:
    if value is None:
        return ""
    digits = re.sub(r"[^\d.]", "", str(value))
    return digits


def _extract_listing_candidates(node: Any, results: List[Dict[str, Any]]) -> None:
    if isinstance(node, dict):
        lower_keys = {str(k).lower(): k for k in node.keys()}
        has_address = any(k in lower_keys for k in ("street", "line", "address", "full_address"))
        has_price = any(k in lower_keys for k in ("list_price", "price", "price_raw", "listprice"))

        if has_address and has_price:
            results.append(node)

        for value in node.values():
            _extract_listing_candidates(value, results)
        return

    if isinstance(node, list):
        for value in node:
            _extract_listing_candidates(value, results)


def fetch_realtor(city, state, limit):
    """
    Realtor.com scraper using page-embedded JSON.
    """
    try:
        query = f"{city}_{state}".replace(" ", "-")
        url = f"https://www.realtor.com/realestateandhomes-search/{query}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        }

        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        script = soup.select_one("script#__NEXT_DATA__")
        if not script or not script.text:
            return []

        payload = json.loads(script.text)
        candidates: List[Dict[str, Any]] = []
        _extract_listing_candidates(payload, candidates)

        listings = []
        seen = set()

        for item in candidates:
            location = item.get("location") or {}
            address_obj = location.get("address") if isinstance(location, dict) else {}
            address = (
                item.get("full_address")
                or item.get("address")
                or item.get("line")
                or address_obj.get("line")
                or address_obj.get("street_name")
                or ""
            )
            if not address:
                continue

            price_raw = item.get("list_price") or item.get("price") or item.get("price_raw") or item.get("listPrice")
            asking_price = _clean_price(price_raw)
            if not asking_price:
                continue

            normalized = address.strip()
            dedupe_key = (normalized.lower(), asking_price)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            listings.append(
                {
                    "address": normalized,
                    "city": city,
                    "state": state,
                    "zip_code": address_obj.get("postal_code", "") if isinstance(address_obj, dict) else "",
                    "asking_price": asking_price,
                }
            )
            if len(listings) >= limit:
                break

        return listings
    except Exception:
        return []
