import requests

def fetch_redfin(city, state, limit):
    """
    Redfin CSV API scraper.
    Returns normalized listing dicts.
    """
    try:
        url = (
            f"https://redfin.com/stingray/api/gis-csv"
            f"?al=1&market={state}&num_homes={limit}&region_id=0"
            f"&region_type=6&status=1&uipt=1,2,3,4,5,6,7"
            f"&v=8&city={city.replace(' ', '%20')}"
        )

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://redfin.com"
        }

        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []

        lines = resp.text.split("\n")
        results = []

        for line in lines[1:limit+1]:
            parts = line.split(",")
            if len(parts) < 10:
                continue

            results.append({
                "address": parts[2],
                "city": city,
                "state": state,
                "zip_code": parts[3],
                "asking_price": parts[4].replace("$", "").replace(",", "")
            })

        return results

    except Exception:
        return []
