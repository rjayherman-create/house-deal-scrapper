import requests
from bs4 import BeautifulSoup
import re

def fetch_craigslist(city, state, limit):
    """
    Craigslist HTML scraper.
    Pulls title + price from result rows.
    """
    try:
        city_slug_hyphen = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")
        city_slug_compact = re.sub(r"[^a-z0-9]", "", city.lower())
        query = f"{city} {state}".strip()
        candidate_urls = [
            f"https://{city_slug_hyphen}.craigslist.org/search/rea",
            f"https://{city_slug_compact}.craigslist.org/search/rea",
            f"https://www.craigslist.org/search/rea?query={query.replace(' ', '+')}",
        ]

        headers = {"User-Agent": "Mozilla/5.0"}
        for url in candidate_urls:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            posts = soup.select(".result-row")[:limit]

            for post in posts:
                title = post.select_one(".result-title")
                price = post.select_one(".result-price")

                if not title or not price:
                    continue

                price_val = re.sub(r"[^\d.]", "", price.text)
                if not price_val:
                    continue

                results.append({
                    "address": title.text.strip(),
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
