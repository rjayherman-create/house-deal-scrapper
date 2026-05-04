import requests
from bs4 import BeautifulSoup
import re

def fetch_zillow(city, state, limit):
    """
    Zillow HTML scraper.
    Extracts price + address from property cards.
    """
    try:
        search = f"{city} {state}".replace(" ", "-")
        url = f"https://www.zillow.com/homes/{search}_rb/"

        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        cards = soup.select("article")[:limit]

        for card in cards:
            price = card.select_one("span[data-test='property-card-price']")
            address = card.select_one("address")

            if not price or not address:
                continue

            price_val = re.sub(r"[^\d.]", "", price.text)

            results.append({
                "address": address.text,
                "city": city,
                "state": state,
                "zip_code": "",
                "asking_price": price_val
            })

        return results

    except Exception:
        return []
