import json
import logging
import re
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _extract_digits(value: Any) -> str:
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
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    city_slug = city.strip().lower().replace(" ", "-")
    state_slug = state.strip().upper()
    candidate_urls = [
        f"https://www.realtor.com/realestateandhomes-search/{city_slug}_{state_slug}",
        f"https://www.realtor.com/realestateandhomes-search/{city_slug}-{state_slug}",
        f"https://www.realtor.com/realestateandhomes-search/{city_slug}",
    ]

    for url in candidate_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            script = soup.select_one("script#__NEXT_DATA__")
            if not script or not script.text:
                logger.warning("Realtor.com: no __NEXT_DATA__ at %s", url)
                continue

            payload = json.loads(script.text)
            candidates: List[Dict[str, Any]] = []
            _extract_listing_candidates(payload, candidates)

            listings = []
            seen = set()

            for item in candidates:
                location = item.get("location") or {}
        address_obj = (location.get("address") if isinstance(location, dict) else None) or {}

                address = (
                    item.get("full_address")
                    or item.get("address")
                    or item.get("line")
                    or (address_obj.get("line") if isinstance(address_obj, dict) else None)
                    or (address_obj.get("street_name") if isinstance(address_obj, dict) else None)
                    or ""
                )
                if not address:
                    continue

                price_raw = (
                    item.get("list_price")
                    or item.get("price")
                    or item.get("price_raw")
                    or item.get("listPrice")
                )
                asking_price = _extract_digits(price_raw)
                if not asking_price:
                    continue

                normalized = address.strip()
                dedupe_key = (
                    normalized.lower(),
                    (city or "").lower(),
                    (state or "").lower(),
                    asking_price,
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                zip_code = ""
                if isinstance(address_obj, dict):
                    zip_code = address_obj.get("postal_code", "") or ""

                listings.append({
                    "address": normalized,
                    "city": city,
                    "state": state,
                    "zip_code": zip_code,
                    "asking_price": asking_price,
                })
                if len(listings) >= limit:
                    break

            if listings:
                logger.info(
                    "Realtor.com: fetched %d listings for %s, %s",
                    len(listings), city, state,
                )
                return listings

        except Exception as exc:
            logger.warning("Realtor.com fetch failed for %s (%s, %s): %s", url, city, state, exc)

    logger.warning("Realtor.com: no listings found for %s, %s", city, state)
    return []
