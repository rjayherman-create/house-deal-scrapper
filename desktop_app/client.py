import os

import requests


API_BASE_URL = os.getenv("HOUSE_DEAL_SCRAPER_API_URL", "http://127.0.0.1:8000").rstrip("/")


def analyze_market(city: str, state: str, include_photos: bool = False):
    response = requests.get(
        f"{API_BASE_URL}/analyze",
        params={
            "city": city,
            "state": state,
            "include_photos": str(include_photos).lower(),
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def fetch_saved_listings(city: str = "", state: str = ""):
    params = {}
    if city:
        params["city"] = city
    if state:
        params["state"] = state

    response = requests.get(f"{API_BASE_URL}/listings", params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("listings", [])
