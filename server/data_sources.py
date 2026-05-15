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
    hud_enabled = _enabled("HUD_USER_TOKEN") or _enabled("HUD_API_TOKEN")
    return [
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
            name="HUD USER FMR API",
            category="official_rent_api",
            required_for_analysis=False,
            enabled=hud_enabled,
            env_var="HUD_USER_TOKEN",
            status="ready" if hud_enabled else "missing_api_key",
            purpose="Official Fair Market Rent source for Section 8/FMR rent values.",
            setup_note="Set HUD_USER_TOKEN or HUD_API_TOKEN in Railway. Without it, Section 8/FMR values show as unavailable.",
        ),
        DataSourceStatus(
            name="Realtime Data Guardrails",
            category="analysis_engine",
            required_for_analysis=True,
            enabled=True,
            env_var=None,
            status="ready",
            purpose="Prevents synthetic comps, fake photos, and fabricated rent/Section 8 values from being displayed as live data.",
            setup_note="When providers are not connected, cards show data unavailable instead of generated filler data.",
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
