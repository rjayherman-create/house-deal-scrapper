import csv
import io
import re

import requests


def _clean_price(value):
    if value is None:
        return ""
    return re.sub(r"[^\d.]", "", str(value))

def fetch_redfin(city, state, limit):
    """
    Redfin CSV API scraper.
    Returns normalized listing dicts.
    """
    try:
        url = (
            f"https://www.redfin.com/stingray/api/gis-csv"
            f"?al=1&num_homes={limit}&region_id=0"
            f"&region_type=6&status=1&uipt=1,2,3,4,5,6,7"
            f"&v=8&city={city.replace(' ', '%20')}&state={state}"
        )

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://redfin.com"
        }

        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []

        reader = csv.DictReader(io.StringIO(resp.text))
        results = []

        for row in reader:
            address = row.get("ADDRESS") or row.get("Street Line")
            price = row.get("PRICE") or row.get("Price")
            if not address or not price:
                continue

            asking_price = _clean_price(price)
            if not asking_price:
                continue

            results.append({
                "address": address,
                "city": row.get("CITY") or city,
                "state": row.get("STATE OR PROVINCE") or state,
                "zip_code": row.get("ZIP OR POSTAL CODE", ""),
                "asking_price": asking_price
            })
            if len(results) >= limit:
                break

        return results

    except Exception:
        return []
