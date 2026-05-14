import logging
import re

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def fetch_craigslist(city, state, limit):
    """
    Craigslist HTML scraper.
    Supports both the legacy result-row layout and the newer cl-static-search-result layout.
    """
    city_slug_hyphen = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")
    city_slug_compact = re.sub(r"[^a-z0-9]", "", city.lower())
    query = f"{city} {state}".strip()
    candidate_urls = [
        f"https://{city_slug_hyphen}.craigslist.org/search/rea",
        f"https://{city_slug_compact}.craigslist.org/search/rea",
        f"https://www.craigslist.org/search/rea?query={query.replace(' ', '+')}",
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    for url in candidate_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            results = []

            # ── New Craigslist layout (2024+) ──────────────────────────────
            new_posts = soup.select("li.cl-static-search-result")
            if new_posts:
                for post in new_posts[:limit]:
                    title_el = (
                        post.select_one(".titlestring")
                        or post.select_one("a.cl-app-anchor")
                    )
                    price_el = post.select_one(".priceinfo")

                    if not title_el or not price_el:
                        continue

                    price_val = re.sub(r"[^\d.]", "", price_el.text)
                    if not price_val:
                        continue

                    results.append({
                        "address": title_el.text.strip(),
                        "city": city,
                        "state": state,
                        "zip_code": "",
                        "asking_price": price_val,
                    })

                if results:
                    logger.info(
                        "Craigslist (new layout): fetched %d listings for %s, %s",
                        len(results), city, state,
                    )
                    return results
                continue

            # ── Legacy Craigslist layout ───────────────────────────────────
            legacy_posts = soup.select(".result-row")[:limit]
            for post in legacy_posts:
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
                    "asking_price": price_val,
                })

            if results:
                logger.info(
                    "Craigslist (legacy layout): fetched %d listings for %s, %s",
                    len(results), city, state,
                )
                return results

        except Exception as exc:
            logger.warning("Craigslist fetch failed for %s (%s, %s): %s", url, city, state, exc)

    logger.warning("Craigslist: no listings found for %s, %s", city, state)
    return []
