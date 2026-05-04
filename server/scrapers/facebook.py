import requests
from bs4 import BeautifulSoup
import re

def fetch_facebook(city, state, limit):
    """
    Facebook Marketplace scraper.
    Works only when FB does not challenge with login.
    """
    try:
        search = f"{city} {state}".replace(" ", "%20")
        url = f"https://www.facebook.com/marketplace/search/?query={search}"

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        }

        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        items = soup.select("a[href*='/marketplace/item']")[:limit]

        for item in items:
            title = item.text.strip()
            price_match = re.search(r"\$([\d,]+)", title)
            price_val = price_match.group(1).replace(",", "") if price_match else "0"

            results.append({
                "address": title,
                "city": city,
                "state": state,
                "zip_code": "",
                "asking_price": price_val
            })

        return results

    except Exception:
        return []
