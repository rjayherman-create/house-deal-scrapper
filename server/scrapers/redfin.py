import csv
import io
import re
from typing import Any

import requests


def _extract_digits(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^\d.]", "", str(value))

def fetch_redfin(city, state, limit):
    """
    Redfin CSV API scraper.
    Returns normalized listing dicts.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://redfin.com"
        }
        params_candidates = [
            {
                "al": 1,
                "num_homes": limit,
                "status": 1,
                "uipt": "1,2,3,4,5,6,7",
                "v": 8,
                "city": city,
                "state": state,
            },
            {
                "al": 1,
                "num_homes": limit,
                "region_type": 6,
                "status": 1,
                "uipt": "1,2,3,4,5,6,7",
                "v": 8,
                "city": city,
                "state": state,
            },
        ]

        for params in params_candidates:
            resp = requests.get(
                "https://www.redfin.com/stingray/api/gis-csv",
                params=params,
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                continue

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
                    "asking_price": asking_price
                })
                if len(results) >= limit:
                    break

            if results:
                return results

        return []

    except Exception:
        return []
