import requests
from bs4 import BeautifulSoup
import re

def fetch_craigslist(city, state, limit):
    """
    Craigslist HTML scraper.
    Pulls title + price from result rows.
    """
    try:
        base = f"https://{city.lower()}.craigslist.org"
        url = f"{base}/search/rea"

        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        results = []
        posts = soup.select(".result-row")[:limit]

        for post in posts:
            title = post.select_one(".result-title")
            price = post.select_one(".result-price")

            if not title or not price:
                continue

            price_val = re.sub(r"[^\d.]", "", price.text)

            results.append({
                "address": title.text,
                "city": city,
                "state": state,
                "zip_code": "",
                "asking_price": price_val
            })

        return results

    except Exception:
        return []
