# engine.py
"""
Unified acquisition-intelligence engine for cheap-property deals.

Sources:
- Redfin
- Zillow
- Realtor.com
- Craigslist
- Facebook Marketplace

Core features:
- Listing aggregation
- Optional photo fetching (all sources)
- Photo age estimation + value categories
- Distress-evidence detection
- System ratings (kitchen, furnace, water heater)
- Comp scoring (gap, density, freshness, similarity)
- Deal scoring (financial + comps + condition + package-seller)
- Buyer questionnaire + walkthrough checklist generation
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import math
import re

# Import real scrapers
from server.scrapers.redfin import fetch_redfin
from server.scrapers.zillow import fetch_zillow
from server.scrapers.realtor import fetch_realtor
from server.scrapers.realty_mole import RealtyMoleAuthenticationError, fetch_realty_mole, is_realty_mole_enabled
from server.scrapers.craigslist import fetch_craigslist
from server.scrapers.facebook import fetch_facebook
from server.scrapers.rentcast import (
    RentCastAuthenticationError,
    fetch_property_record,
    fetch_rent_estimate,
    fetch_rentcast,
    fetch_value_estimate,
    is_rentcast_enabled,
)
from server.location_normalizer import normalize_location
from server.low_cost_data_engine import estimate_rent, estimate_section8_rent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------

PHOTO_AGE_BUCKETS = [
    ("fresh", 0, 6, 1.00),
    ("recent", 6, 12, 0.90),
    ("mid_aged", 12, 24, 0.75),
    ("outdated", 24, 120, 0.60),
    ("completely_useless", 120, 10_000, 0.30),
]


@dataclass
class PhotoAnalysis:
    estimated_age_months: Optional[float]
    category: str
    value_score: float
    distress_evidence: bool
    notes: str


@dataclass
class SystemRatings:
    kitchen_score: float
    furnace_score: float
    water_heater_score: float
    system_condition_score: float
    notes: str


@dataclass
class CompAnalysis:
    comp_gap_score: float
    comp_density_score: float
    comp_freshness_score: float
    comp_similarity_score: float
    photo_age_multiplier: float
    comp_score: float
    notes: str


@dataclass
class DealScores:
    financial_score: float
    comp_score: float
    condition_score: float
    package_seller_score: float
    final_score: float


@dataclass
class Listing:
    source: str
    source_id: str
    address: str
    city: str
    state: str
    price: float
    beds: Optional[float]
    baths: Optional[float]
    sqft: Optional[float]
    year_built: Optional[int]
    photos: List[str]
    description: str
    seller_contact: Optional[str]
    raw_data: Dict[str, Any]


@dataclass
class ListingAnalysis:
    listing: Listing
    photo_analysis: PhotoAnalysis
    system_ratings: SystemRatings
    comp_analysis: CompAnalysis
    deal_scores: DealScores
    questionnaire: Dict[str, Any]


# ---------------------------------------------------------------------
# AI helpers (stubs – connect to Groq/OpenAI here)
# ---------------------------------------------------------------------

def ai_estimate_photo_age_and_distress(photos: List[str], description: str) -> PhotoAnalysis:
    if not photos:
        return PhotoAnalysis(
            estimated_age_months=None,
            category="unknown",
            value_score=0.5,
            distress_evidence=False,
            notes="No photos available; default medium uncertainty."
        )

    estimated_age_months = 18.0
    category, value_score = bucket_photo_age(estimated_age_months)
    return PhotoAnalysis(
        estimated_age_months=estimated_age_months,
        category=category,
        value_score=value_score,
        distress_evidence=False,
        notes="Placeholder AI estimate; integrate real vision model."
    )


def ai_rate_systems(photos: List[str], description: str) -> SystemRatings:
    kitchen_score = 1.0
    furnace_score = 0.8
    water_heater_score = 0.8

    system_condition_score = (kitchen_score + furnace_score + water_heater_score) / 3.0
    return SystemRatings(
        kitchen_score=kitchen_score,
        furnace_score=furnace_score,
        water_heater_score=water_heater_score,
        system_condition_score=system_condition_score,
        notes="Placeholder system ratings; integrate real AI analysis."
    )


def ai_compute_financial_score(listing: Listing) -> float:
    value_estimate = listing.raw_data.get("value_estimate") or {}
    rent_estimate = listing.raw_data.get("rent_estimate") or {}
    estimated_value = parse_optional_float(
        value_estimate.get("price")
        or value_estimate.get("value")
        or value_estimate.get("estimatedValue")
        or value_estimate.get("median")
    )
    estimated_rent = parse_optional_float(
        rent_estimate.get("rent")
        or rent_estimate.get("price")
        or rent_estimate.get("estimatedRent")
        or rent_estimate.get("median")
        or listing.raw_data.get("low_cost_rent_estimate")
        or listing.raw_data.get("section8_estimate")
    )

    price_score = 0.5
    if estimated_value and listing.price:
        discount = (estimated_value - listing.price) / estimated_value
        price_score = max(0.0, min(1.0, 0.45 + discount * 1.6))

    rent_score = 0.5
    if estimated_rent and listing.price:
        annual_rent_yield = (estimated_rent * 12) / listing.price
        rent_score = max(0.0, min(1.0, annual_rent_yield / 0.14))

    return round(0.7 * price_score + 0.3 * rent_score, 3)


def ai_detect_package_seller(listing: Listing, all_listings: List[Listing]) -> float:
    return 0.3


# ---------------------------------------------------------------------
# Photo age bucketing
# ---------------------------------------------------------------------

def bucket_photo_age(age_months: float) -> (str, float):
    for name, low, high, multiplier in PHOTO_AGE_BUCKETS:
        if low <= age_months < high:
            return name, multiplier
    return "unknown", 0.5


# ---------------------------------------------------------------------
# Comp scoring
# ---------------------------------------------------------------------

def compute_comp_gap_score(listing_price: float, median_comp_price: Optional[float]) -> float:
    if not median_comp_price or median_comp_price <= 0:
        return 0.5
    comp_gap = (median_comp_price - listing_price) / median_comp_price
    return max(0.0, min(1.0, 0.5 + comp_gap))


def compute_comp_density_score(num_comps: int) -> float:
    return 1.0 - math.exp(-num_comps / 5.0)


def compute_comp_freshness_score(avg_comp_age_months: Optional[float]) -> float:
    if avg_comp_age_months is None:
        return 0.5
    if avg_comp_age_months <= 12:
        return 1.0
    if avg_comp_age_months >= 60:
        return 0.3
    return 1.0 - (avg_comp_age_months - 12) * (0.7 / 48.0)


def compute_comp_similarity_score(listing: Listing, comps: List[Dict[str, Any]]) -> float:
    if not comps:
        return 0.5
    return 0.7


def compute_photo_age_multiplier(photo_analysis: PhotoAnalysis) -> float:
    for name, _, _, mult in PHOTO_AGE_BUCKETS:
        if name == photo_analysis.category:
            return mult
    return 0.5


def compute_comp_analysis(listing: Listing, photo_analysis: PhotoAnalysis, comps: List[Dict[str, Any]]) -> CompAnalysis:
    comp_prices = sorted(
        price
        for price in (
            parse_optional_float(c.get("price") or c.get("salePrice") or c.get("listPrice") or c.get("value"))
            for c in comps
        )
        if price and price > 0
    )
    median_comp_price = None
    if comp_prices:
        mid = len(comp_prices) // 2
        median_comp_price = comp_prices[mid] if len(comp_prices) % 2 else (comp_prices[mid - 1] + comp_prices[mid]) / 2

    comp_days = [
        days
        for days in (parse_optional_float(c.get("daysOld") or c.get("days_on_market")) for c in comps)
        if days is not None
    ]
    avg_comp_age_months = (sum(comp_days) / len(comp_days) / 30) if comp_days else None
    num_comps = len(comps)

    comp_gap_score = compute_comp_gap_score(listing.price, median_comp_price)
    comp_density_score = compute_comp_density_score(num_comps)
    comp_freshness_score = compute_comp_freshness_score(avg_comp_age_months)
    comp_similarity_score = compute_comp_similarity_score(listing, comps)
    photo_age_multiplier = compute_photo_age_multiplier(photo_analysis)

    base_comp_score = (
        0.35 * comp_gap_score +
        0.25 * comp_density_score +
        0.20 * comp_freshness_score +
        0.20 * comp_similarity_score
    )
    comp_score = base_comp_score * photo_age_multiplier

    return CompAnalysis(
        comp_gap_score=comp_gap_score,
        comp_density_score=comp_density_score,
        comp_freshness_score=comp_freshness_score,
        comp_similarity_score=comp_similarity_score,
        photo_age_multiplier=photo_age_multiplier,
        comp_score=comp_score,
        notes=(
            f"Based on {num_comps} live comparable record(s)."
            if num_comps
            else "No live comparable records were available; score uses conservative defaults."
        )
    )


# ---------------------------------------------------------------------
# Deal scoring
# ---------------------------------------------------------------------

def compute_deal_scores(listing: Listing, photo_analysis: PhotoAnalysis, system_ratings: SystemRatings, comp_analysis: CompAnalysis, package_seller_score: float) -> DealScores:
    financial_score = ai_compute_financial_score(listing)

    condition_base = system_ratings.system_condition_score
    if photo_analysis.distress_evidence:
        condition_base *= 0.3

    condition_score = max(0.0, min(1.0, condition_base))

    final_score = (
        0.40 * financial_score +
        0.30 * comp_analysis.comp_score +
        0.20 * condition_score +
        0.10 * package_seller_score
    )

    return DealScores(
        financial_score=financial_score,
        comp_score=comp_analysis.comp_score,
        condition_score=condition_score,
        package_seller_score=package_seller_score,
        final_score=final_score
    )


# ---------------------------------------------------------------------
# Questionnaire & checklist generation
# ---------------------------------------------------------------------

def generate_questionnaire(analysis: ListingAnalysis) -> Dict[str, Any]:
    l = analysis.listing
    pa = analysis.photo_analysis
    sr = analysis.system_ratings

    sections = []

    sections.append({
        "title": "Kitchen",
        "questions": [
            "Is the kitchen currently functional?",
            "Are all appliances included and working?",
            "Has there been any water damage under the sink or behind appliances?",
            "When were the cabinets and counters last updated?",
            "Are there any plumbing or electrical issues in the kitchen?"
        ]
    })

    sections.append({
        "title": "Furnace / Heating",
        "questions": [
            "What is the age of the furnace?",
            "When was it last serviced?",
            "Is it currently operational?",
            "Has the property ever had heating issues or code violations?",
            "Is the ductwork intact and connected?"
        ]
    })

    sections.append({
        "title": "Water Heater",
        "questions": [
            "What is the age of the water heater?",
            "Is it currently producing hot water?",
            "Has it ever leaked or been replaced?",
            "Is it properly vented?"
        ]
    })

    if pa.distress_evidence:
        sections.append({
            "title": "Distress Evidence",
            "questions": [
                "Why are windows or doors boarded?",
                "When did the last tenant move out?",
                "Did they leave belongings behind?",
                "Has the property been professionally cleaned?",
                "Are there any city violations or condemnation notices?"
            ]
        })

    sections.append({
        "title": "Vacancy & Utilities",
        "questions": [
            "How long has the property been vacant (if at all)?",
            "Are all utilities currently on (water, gas, electric)? If not, why?",
            "Has the property ever had frozen pipes?",
            "Are there any liens from utility companies?"
        ]
    })

    sections.append({
        "title": "Seller Motivation & Portfolio",
        "questions": [
            "Why are you selling now?",
            "Do you have other properties for sale?",
            "Are you open to selling multiple properties as a package?",
            "Are any of the properties tenant-occupied?",
            "Are any currently vacant or distressed?"
        ]
    })

    sections.append({
        "title": "Legal & Financial",
        "questions": [
            "Are there any back taxes owed?",
            "Are there any liens or judgments on the property?",
            "Is the title clean?",
            "Has the property been used as a rental?",
            "Are there any Section 8 inspections or violations?"
        ]
    })

    checklist = {
        "exterior": [
            "Roof condition",
            "Siding condition",
            "Foundation cracks",
            "Windows intact or boarded",
            "Doors intact or missing",
            "Signs of squatters or forced entry"
        ],
        "interior": [
            "Kitchen functional",
            "Furnace present & operational",
            "Water heater present & operational",
            "Electrical panel condition",
            "Plumbing leaks",
            "Mold or water damage",
            "Trash, belongings, hoarder debris",
            "Missing fixtures or appliances"
        ],
        "neighborhood": [
            "Vacant houses nearby",
            "Boarded houses nearby",
            "Crime indicators",
            "Market comps",
            "Rental demand"
        ]
    }

    return {
        "property": {
            "address": l.address,
            "city": l.city,
            "state": l.state,
            "price": l.price,
        },
        "photo_summary": {
            "age_category": pa.category,
            "distress_evidence": pa.distress_evidence,
            "notes": pa.notes,
        },
        "system_summary": {
            "kitchen_score": sr.kitchen_score,
            "furnace_score": sr.furnace_score,
            "water_heater_score": sr.water_heater_score,
            "notes": sr.notes,
        },
        "sections": sections,
        "checklist": checklist,
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z"
        }
    }


# ---------------------------------------------------------------------
# Main search entrypoint
# ---------------------------------------------------------------------

def parse_optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        cleaned = re.sub(r"[^\d.]", "", str(value))
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None


def extract_rentcast_comps(value_estimate: Dict[str, Any]) -> List[Dict[str, Any]]:
    comps = value_estimate.get("comparables") or value_estimate.get("comps") or []
    return comps if isinstance(comps, list) else []


def enrich_listing(listing: Listing) -> Listing:
    if not is_rentcast_enabled():
        return listing

    address = ", ".join(part for part in [listing.address, listing.city, listing.state] if part)
    try:
        property_record = fetch_property_record(address)
    except Exception:
        property_record = {}
    try:
        value_estimate = fetch_value_estimate(address, comp_count=10)
    except Exception:
        value_estimate = {}
    try:
        rent_estimate = fetch_rent_estimate(address, comp_count=10)
    except Exception:
        rent_estimate = {}

    merged_raw = dict(listing.raw_data)
    merged_raw["property_record"] = property_record
    merged_raw["value_estimate"] = value_estimate
    merged_raw["rent_estimate"] = rent_estimate
    merged_raw["low_cost_rent_estimate"] = estimate_rent({
        "bedrooms": listing.beds,
        "sqft": listing.sqft,
        "city": listing.city,
        "state": listing.state,
    })
    merged_raw["section8_estimate"] = estimate_section8_rent(listing.beds, listing.city, listing.state)

    subject = value_estimate.get("subjectProperty") if isinstance(value_estimate, dict) else {}
    subject = subject if isinstance(subject, dict) else {}
    listing.beds = listing.beds or parse_optional_float(subject.get("bedrooms") or property_record.get("bedrooms"))
    listing.baths = listing.baths or parse_optional_float(subject.get("bathrooms") or property_record.get("bathrooms"))
    listing.sqft = listing.sqft or parse_optional_float(subject.get("squareFootage") or property_record.get("squareFootage"))
    listing.year_built = listing.year_built or subject.get("yearBuilt") or property_record.get("yearBuilt")
    listing.raw_data = merged_raw
    if not listing.photos:
        listing.photos = extract_photos(merged_raw, include_photos=True)
    return listing

def extract_photos(raw: Dict[str, Any], include_photos: bool, limit: int = 12) -> List[str]:
    if not include_photos:
        return []
    photos = []
    seen = set()
    image_keys = {
        "photo",
        "photos",
        "photourl",
        "photourls",
        "image",
        "images",
        "imageurl",
        "imageurls",
        "src",
        "href",
        "url",
        "small",
        "medium",
        "large",
    }

    def visit(value: Any, key_hint: str = "") -> None:
        if len(photos) >= limit:
            return
        normalized_key = key_hint.lower().replace("_", "").replace("-", "")
        if isinstance(value, str):
            lower = value.lower()
            looks_like_image = any(token in lower for token in [".jpg", ".jpeg", ".png", ".webp", "photos", "image"])
            if value.startswith("http") and (normalized_key in image_keys or looks_like_image) and value not in seen:
                seen.add(value)
                photos.append(value)
            return
        if isinstance(value, list):
            for item in value:
                visit(item, key_hint)
            return
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, str(key))

    visit(raw)
    return photos[:limit]


def search_listings(
    city: str,
    state: str,
    include_photos: bool = False,
    max_price: Optional[float] = None,
) -> List[ListingAnalysis]:
    city, state, _ = normalize_location(city, state)
    listings_raw = []
    seen_listings = set()

    def parse_price(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        if not text:
            return None

        cleaned = re.sub(r"[^\d.]", "", text)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    # Pull from all scrapers
    scrapers = []
    if is_realty_mole_enabled():
        scrapers.append(("Realty Mole", fetch_realty_mole))
    scrapers.extend([
        ("Redfin", fetch_redfin),
        ("Zillow", fetch_zillow),
        ("Realtor", fetch_realtor),
        ("Craigslist", fetch_craigslist),
        ("Facebook", fetch_facebook),
    ])
    if is_rentcast_enabled():
        scrapers.append(("RentCast", fetch_rentcast))

    for source_name, scraper in scrapers:
        try:
            results = scraper(city, state, limit=20)
            logger_count = len(results) if results else 0
            logger.info(
                "%s scraper returned %d candidate listing(s) for %s, %s",
                source_name,
                logger_count,
                city,
                state,
            )
            for r in results:
                address = (r.get("address") or "").strip()
                price = parse_price(r.get("asking_price"))
                if not address or price is None:
                    continue
                if max_price is not None and price > max_price:
                    continue

                dedupe_key = (
                    source_name.lower(),
                    address.lower(),
                    (r.get("city") or city).lower(),
                    (r.get("state") or state).lower(),
                )
                if dedupe_key in seen_listings:
                    continue
                seen_listings.add(dedupe_key)

                normalized = dict(r)
                normalized["address"] = address
                normalized["asking_price"] = price
                listings_raw.append((source_name, normalized))
        except (RentCastAuthenticationError, RealtyMoleAuthenticationError):
            raise
        except Exception as exc:
            logger.warning(
                "%s scraper failed for %s, %s: %s",
                source_name,
                city,
                state,
                exc,
            )
            continue

    analyses = []

    for source_name, raw in listings_raw:
        listing = Listing(
            source=source_name,
            source_id=raw.get("source_id") or raw.get("address", ""),
            address=raw.get("address", ""),
            city=raw.get("city", city),
            state=raw.get("state", state),
            price=raw["asking_price"],
            beds=parse_optional_float(raw.get("beds")),
            baths=parse_optional_float(raw.get("baths")),
            sqft=parse_optional_float(raw.get("sqft")),
            year_built=raw.get("year_built"),
            photos=extract_photos(raw, include_photos),
            description=raw.get("description") or "",
            seller_contact=None,
            raw_data=raw
        )
        listing = enrich_listing(listing)

        photo_analysis = ai_estimate_photo_age_and_distress(listing.photos, listing.description)
        system_ratings = ai_rate_systems(listing.photos, listing.description)

        comps = extract_rentcast_comps(listing.raw_data.get("value_estimate") or {})
        comp_analysis = compute_comp_analysis(listing, photo_analysis, comps)

        package_seller_score = ai_detect_package_seller(listing, [])

        deal_scores = compute_deal_scores(
            listing=listing,
            photo_analysis=photo_analysis,
            system_ratings=system_ratings,
            comp_analysis=comp_analysis,
            package_seller_score=package_seller_score,
        )

        dummy = ListingAnalysis(
            listing=listing,
            photo_analysis=photo_analysis,
            system_ratings=system_ratings,
            comp_analysis=comp_analysis,
            deal_scores=deal_scores,
            questionnaire={}
        )

        questionnaire = generate_questionnaire(dummy)

        analyses.append(
            ListingAnalysis(
                listing=listing,
                photo_analysis=photo_analysis,
                system_ratings=system_ratings,
                comp_analysis=comp_analysis,
                deal_scores=deal_scores,
                questionnaire=questionnaire
            )
        )

    return analyses


# ---------------------------------------------------------------------
# Utility: serialize for GUI / API
# ---------------------------------------------------------------------

def serialize_analysis(analysis: ListingAnalysis) -> Dict[str, Any]:
    return {
        "listing": asdict(analysis.listing),
        "photo_analysis": asdict(analysis.photo_analysis),
        "system_ratings": asdict(analysis.system_ratings),
        "comp_analysis": asdict(analysis.comp_analysis),
        "deal_scores": asdict(analysis.deal_scores),
        "questionnaire": analysis.questionnaire,
    }


if __name__ == "__main__":
    results = search_listings("Cleveland", "OH", include_photos=False)
    print(f"Found {len(results)} listings")
    for r in results[:3]:
        print(serialize_analysis(r))
