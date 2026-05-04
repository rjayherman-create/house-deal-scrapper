import requests

API_URL = "https://house-deal-scrapper-production.up.railway.app"

def analyze_listing(data: dict):
    url = f"{API_URL}/api/listings/analyze"
    response = requests.post(url, json=data, timeout=20)
    response.raise_for_status()
    return response.json()
