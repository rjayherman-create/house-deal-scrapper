# engine.py
"""
Unified acquisition-intelligence engine for cheap-property deals.

Sources:
- Redfin
- Zillow
- Realtor.com
- Craigslist

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
import math

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
    kitchen_score: float      # 1.0 functional, 0.5 partial, 0.0 non-functional
    furnace_score: float      # same scale
    water_heater_score: float # same scale
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
    photos: List[str]  # URLs or identifiers
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
# Fetchers (stubs – you’ll wire real scraping/API logic here)
# ---------------------------------------------------------------------

def fetch_redfin(city: str, state: str, include_photos: bool) -> List[Listing]:
    # TODO: implement real Redfin fetch
    return []


def fetch_zillow(city: str, state: str, include_photos: bool) -> List[Listing]:
    # TODO: implement real Zillow fetch
    return []


def fetch_realtor(city: str, state: str, include_photos: bool) -> List[Listing]:
    # TODO: implement real Realtor.com fetch
    return []


def fetch_craigslist(city: str, state: str, include_photos: bool) -> List[Listing]:
    # TODO: implement real Craigslist fetch
    return []


# ---------------------------------------------------------------------
# AI helpers (stubs – connect to Groq/OpenAI here)
# ---------------------------------------------------------------------

def ai_estimate_photo_age_and_distress(photos: List[str], description: str) -> PhotoAnalysis:
    """
    Use OpenAI/Groq vision + text to:
    - estimate photo age (months)
    - detect distress evidence (boarded windows, trash, missing doors, etc.)
    - assign category + value_score
    """
    # TODO: call vision model; here is a placeholder heuristic
    if not photos:
        return PhotoAnalysis(
            estimated_age_months=None,
            category="unknown",
            value_score=0.5,
            distress_evidence=False,
            notes="No photos available; default medium uncertainty."
        )

    # Placeholder: assume mid-aged, no distress
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
    """
    Use AI to rate:
    - kitchen functional / partial / non-functional
    - furnace condition
    - water heater condition
    """
    # TODO: call vision + text model; placeholder logic
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
    """
    Use rent estimates, taxes, etc. to compute a financial score (0–1).
    """
    # TODO: integrate real underwriting logic
    return 0.7


def ai_detect_package_seller(listing: Listing, all_listings: List[Listing]) -> float:
    """
    Detect if seller is likely a package seller (0–1).
    """
    # TODO: use phone/email reuse, patterns, etc.
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
    # Map comp_gap to 0–1, clipping extremes
    return max(0.0, min(1.0, 0.5 + comp_gap))


def compute_comp_density_score(num_comps: int) -> float:
    # Simple saturation curve: 0 comps -> 0, 10+ comps -> ~1
    return 1.0 - math.exp(-num_comps / 5.0)


def compute_comp_freshness_score(avg_comp_age_months: Optional[float]) -> float:
    if avg_comp_age_months is None:
        return 0.5
    if avg_comp_age_months <= 12:
        return 1.0
    if avg_comp_age_months >= 60:
        return 0.3
    # Linear between 12 and 60
    return 1.0 - (avg_comp_age_months - 12) * (0.7 / 48.0)


def compute_comp_similarity_score(listing: Listing, comps: List[Dict[str, Any]]) -> float:
    # TODO: implement real similarity (beds, baths, sqft, year, condition)
    if not comps:
        return 0.5
    return 0.7


def compute_photo_age_multiplier(photo_analysis: PhotoAnalysis) -> float:
    if photo_analysis.category == "distress_evidence":
        # Distress evidence is highly valuable but reduces comp confidence
        return 0.5
    for name, _, _, mult in PHOTO_AGE_BUCKETS:
        if name == photo_analysis.category:
            return mult
    return 0.5


def compute_comp_analysis(
    listing: Listing,
    photo_analysis: PhotoAnalysis,
    comps: List[Dict[str, Any]]
) -> CompAnalysis:
    # Placeholder comp stats
    median_comp_price = None
    avg_comp_age_months = None
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
        notes="Placeholder comp analysis; wire real comps + stats."
    )


# ---------------------------------------------------------------------
# Deal scoring
# ---------------------------------------------------------------------

def compute_deal_scores(
    listing: Listing,
    photo_analysis: PhotoAnalysis,
    system_ratings: SystemRatings,
    comp_analysis: CompAnalysis,
    package_seller_score: float
) -> DealScores:
    financial_score = ai_compute_financial_score(listing)

    # Condition score: systems + distress
    condition_base = system_ratings.system_condition_score
    if photo_analysis.distress_evidence:
        condition_base *= 0.3  # severe distress

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

    # Kitchen
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

    # Furnace
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

    # Water heater
    sections.append({
        "title": "Water Heater",
        "questions": [
            "What is the age of the water heater?",
            "Is it currently producing hot water?",
            "Has it ever leaked or been replaced?",
            "Is it properly vented?"
        ]
    })

    # Distress evidence
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

    # Vacancy / utilities
    sections.append({
        "title": "Vacancy & Utilities",
        "questions": [
            "How long has the property been vacant (if at all)?",
            "Are all utilities currently on (water, gas, electric)? If not, why?",
            "Has the property ever had frozen pipes?",
            "Are there any liens from utility companies?"
        ]
    })

    # Seller motivation / portfolio
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

    # Legal / financial
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

    # Walkthrough checklist
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

def search_listings(
    city: str,
    state: str,
    include_photos: bool = False
) -> List[ListingAnalysis]:
    """
    Unified entrypoint:
    - fetch from all sources
    - analyze photos, systems, comps, deal score
    - generate questionnaire/checklist
    """
    listings: List[Listing] = []
    listings += fetch_redfin(city, state, include_photos)
    listings += fetch_zillow(city, state, include_photos)
    listings += fetch_realtor(city, state, include_photos)
    listings += fetch_craigslist(city, state, include_photos)

    analyses: List[ListingAnalysis] = []

    for listing in listings:
        photo_analysis = ai_estimate_photo_age_and_distress(listing.photos, listing.description)
        system_ratings = ai_rate_systems(listing.photos, listing.description)

        # TODO: fetch real comps for this listing
        comps: List[Dict[str, Any]] = []
        comp_analysis = compute_comp_analysis(listing, photo_analysis, comps)

        package_seller_score = ai_detect_package_seller(listing, listings)

        deal_scores = compute_deal_scores(
            listing=listing,
            photo_analysis=photo_analysis,
            system_ratings=system_ratings,
            comp_analysis=comp_analysis,
            package_seller_score=package_seller_score,
        )

        # Temporary placeholder; we regenerate after we have the object
        dummy_analysis = ListingAnalysis(
            listing=listing,
            photo_analysis=photo_analysis,
            system_ratings=system_ratings,
            comp_analysis=comp_analysis,
            deal_scores=deal_scores,
            questionnaire={}
        )
        questionnaire = generate_questionnaire(dummy_analysis)

        analysis = ListingAnalysis(
            listing=listing,
            photo_analysis=photo_analysis,
            system_ratings=system_ratings,
            comp_analysis=comp_analysis,
            deal_scores=deal_scores,
            questionnaire=questionnaire
        )
        analyses.append(analysis)

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
    # Simple manual test stub
    results = search_listings("Cleveland", "OH", include_photos=False)
    print(f"Found {len(results)} listings")
    for r in results[:3]:
        print(serialize_analysis(r))
