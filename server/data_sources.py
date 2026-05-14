import os
from dataclasses import asdict, dataclass
from typing import List, Optional


@dataclass
class DataSourceStatus:
    name: str
    category: str
    required_for_analysis: bool
    enabled: bool
    env_var: Optional[str]
    status: str
    purpose: str
    setup_note: str


def _enabled(env_var: Optional[str]) -> bool:
    return bool(env_var and (os.getenv(env_var) or "").strip())


def _rentcast_enabled() -> bool:
    enabled_flag = (os.getenv("RENTCAST_ENABLED") or "false").strip().lower()
    return enabled_flag in {"1", "true", "yes"} and _enabled("RENTCAST_API_KEY")


def get_data_sources() -> List[DataSourceStatus]:
    realty_mole_enabled = _enabled("REALTY_MOLE_API_KEY") or _enabled("RAPIDAPI_KEY")
    return [
        DataSourceStatus(
            name="Realty Mole",
            category="live_listing_api",
            required_for_analysis=False,
            enabled=realty_mole_enabled,
            env_var="REALTY_MOLE_API_KEY",
            status="ready" if realty_mole_enabled else "missing_api_key",
            purpose="Provider-backed live sale listing feed used before brittle website scraping.",
            setup_note="Set REALTY_MOLE_API_KEY or RAPIDAPI_KEY in Railway to enable live sale listings, photos, and normalized property fields.",
        ),
        DataSourceStatus(
            name="RentCast",
            category="premium_api",
            required_for_analysis=False,
            enabled=_rentcast_enabled(),
            env_var="RENTCAST_ENABLED",
            status="premium_enabled" if _rentcast_enabled() else "premium_disabled",
            purpose="Optional future premium enrichment for high-score or paid user deep analysis only.",
            setup_note="Disabled by default to control costs. Set RENTCAST_ENABLED=true only when premium enrichment is intentionally enabled.",
        ),
        DataSourceStatus(
            name="Low-Cost Data Engine",
            category="primary_engine",
            required_for_analysis=True,
            enabled=True,
            env_var=None,
            status="ready",
            purpose="Primary default strategy using cached intelligence, public scrape data, internal rent estimates, and Section 8 estimates.",
            setup_note="No paid API key required.",
        ),
        DataSourceStatus(
            name="Redfin CSV",
            category="fallback_scrape",
            required_for_analysis=False,
            enabled=True,
            env_var=None,
            status="fallback_only",
            purpose="Backup sale listing discovery when public CSV access is available.",
            setup_note="No key required, but requests can be blocked or return zero results from hosted servers.",
        ),
        DataSourceStatus(
            name="Realtor.com",
            category="fallback_scrape",
            required_for_analysis=False,
            enabled=True,
            env_var=None,
            status="fallback_only",
            purpose="Backup sale listing discovery from page-embedded data.",
            setup_note="No key required, but HTML shape and anti-bot controls can change.",
        ),
        DataSourceStatus(
            name="Craigslist",
            category="fallback_scrape",
            required_for_analysis=False,
            enabled=True,
            env_var=None,
            status="fallback_only",
            purpose="Low-cost/off-market style backup source for FSBO and local real-estate posts.",
            setup_note="No key required; quality varies by market.",
        ),
        DataSourceStatus(
            name="Zillow",
            category="fallback_scrape",
            required_for_analysis=False,
            enabled=True,
            env_var=None,
            status="fallback_only",
            purpose="Best-effort backup source only.",
            setup_note="Direct scraping can be blocked; use API-backed sources for production reliability.",
        ),
        DataSourceStatus(
            name="Facebook Marketplace",
            category="fallback_scrape",
            required_for_analysis=False,
            enabled=False,
            env_var=None,
            status="manual_or_browser_required",
            purpose="Potential seller lead source.",
            setup_note="Usually requires login/browser automation, so server-side scraping is not reliable.",
        ),
    ]


def serialize_data_sources() -> List[dict]:
    return [asdict(source) for source in get_data_sources()]


def has_primary_listing_source() -> bool:
    return any(source.required_for_analysis and source.enabled for source in get_data_sources())
