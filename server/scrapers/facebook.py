import requests
from bs4 import BeautifulSoup
import re

def fetch_facebook(city, state, limit):
    """
    Facebook Marketplace scraper.
    Works only when FB does not challenge with login.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        }
        search = f"{city} {state}".strip().replace(" ", "%20")
        city_slug = city.strip().lower().replace(" ", "-")
        candidate_urls = [
            f"https://www.facebook.com/marketplace/search/?query={search}",
            f"https://www.facebook.com/marketplace/{city_slug}/search/?query={search}",
        ]

        for url in candidate_urls:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            items = soup.select("a[href*='/marketplace/item']")[:limit]

            for item in items:
                title = item.text.strip()
                price_match = re.search(r"\$([\d,]+)", title)
                if not price_match:
                    continue
                price_val = price_match.group(1).replace(",", "")

                results.append({
                    "address": title,
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
