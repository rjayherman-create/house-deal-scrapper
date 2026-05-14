import requests
from bs4 import BeautifulSoup
import re

def fetch_zillow(city, state, limit):
    """
    Zillow HTML scraper.
    Extracts price + address from property cards.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        city_slug = city.strip().lower().replace(" ", "-")
        state_upper = state.strip().upper()
        state_lower = state.strip().lower()
        candidate_urls = [
            f"https://www.zillow.com/homes/for_sale/{city_slug}-{state_upper}/",
            f"https://www.zillow.com/homes/{city_slug}-{state_upper}_rb/",
            f"https://www.zillow.com/homes/{city_slug}-{state_lower}_rb/",
            f"https://www.zillow.com/homes/{city_slug}_{state_upper}_rb/",
            f"https://www.zillow.com/homes/{city_slug}_{state_lower}_rb/",
        ]

        for url in candidate_urls:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            cards = soup.select("article")
            if not cards:
                cards = soup.select("[data-test='property-card']")
            cards = cards[:limit]

            for card in cards:
                price = (
                    card.select_one("span[data-test='property-card-price']")
                    or card.select_one("[data-test='property-card-price']")
                )
                address = (
                    card.select_one("address")
                    or card.select_one("[data-test='property-card-addr']")
                    or card.select_one("[data-test='property-card-address']")
                )

                if not price or not address:
                    continue

                price_val = re.sub(r"[^\d.]", "", price.text)
                if not price_val:
                    continue

                results.append({
                    "address": address.text.strip(),
                    "city": city,
                    "state": state,
                    "zip_code": "",
                    "asking_price": price_val
                })

            if results:
                return results

        return []

    except Exception:
        return []
