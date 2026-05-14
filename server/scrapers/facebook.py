import logging
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def fetch_facebook(city, state, limit):
    """
    Facebook Marketplace scraper.
    Works only when FB does not challenge with login.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    search = f"{city} {state}".strip().replace(" ", "%20")
    city_slug = city.strip().lower().replace(" ", "-")
    candidate_urls = [
        f"https://www.facebook.com/marketplace/search/?query={search}",
        f"https://www.facebook.com/marketplace/{city_slug}/search/?query={search}",
    ]

    for url in candidate_urls:
        try:
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
                    "asking_price": price_val,
                })

            if results:
                logger.info(
                    "Facebook: fetched %d listings for %s, %s", len(results), city, state
                )
                return results

        except Exception as exc:
            logger.warning("Facebook fetch failed for %s (%s, %s): %s", url, city, state, exc)

    logger.warning("Facebook: no listings found for %s, %s (login likely required)", city, state)
    return []
