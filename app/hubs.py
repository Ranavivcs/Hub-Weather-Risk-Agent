"""The hub network. ASSUMPTION: the brief names no hubs, so these 15 are chosen by us.

Choice: every city the example questions name (Miami, Houston, Denver, Dallas), six Midwest hubs so a
Midwest ranking is meaningful, well-known US freight centers, and a spread of hazard profiles.
Coordinates are city centers; `county_fips` links a hub to FEMA National Risk Index county data.
Regions follow the US Census Bureau definitions.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Hub:
    id: str
    name: str
    state: str
    region: str  # "Midwest" | "South" | "West" | "Northeast"
    lat: float
    lon: float
    county_fips: str
    county_name: str


HUBS: tuple[Hub, ...] = (
    Hub("chicago", "Chicago", "IL", "Midwest", 41.88, -87.63, "17031", "Cook"),
    Hub("indianapolis", "Indianapolis", "IN", "Midwest", 39.77, -86.16, "18097", "Marion"),
    Hub("columbus", "Columbus", "OH", "Midwest", 39.96, -83.00, "39049", "Franklin"),
    Hub("minneapolis", "Minneapolis", "MN", "Midwest", 44.98, -93.27, "27053", "Hennepin"),
    Hub("kansas_city", "Kansas City", "MO", "Midwest", 39.10, -94.58, "29095", "Jackson"),
    Hub("st_louis", "St. Louis", "MO", "Midwest", 38.63, -90.20, "29510", "St. Louis city"),
    Hub("dallas", "Dallas", "TX", "South", 32.78, -96.80, "48113", "Dallas"),
    Hub("houston", "Houston", "TX", "South", 29.76, -95.37, "48201", "Harris"),
    Hub("atlanta", "Atlanta", "GA", "South", 33.75, -84.39, "13121", "Fulton"),
    Hub("memphis", "Memphis", "TN", "South", 35.15, -90.05, "47157", "Shelby"),
    Hub("miami", "Miami", "FL", "South", 25.76, -80.19, "12086", "Miami-Dade"),
    Hub("denver", "Denver", "CO", "West", 39.74, -104.99, "08031", "Denver"),
    Hub("phoenix", "Phoenix", "AZ", "West", 33.45, -112.07, "04013", "Maricopa"),
    Hub("los_angeles", "Los Angeles", "CA", "West", 34.05, -118.24, "06037", "Los Angeles"),
    Hub("newark", "Newark", "NJ", "Northeast", 40.74, -74.17, "34013", "Essex"),
)

REGIONS = ("Midwest", "South", "West", "Northeast")

_BY_KEY = {key: hub for hub in HUBS for key in (hub.id, hub.name.lower())}


def find_hub(name_or_id: str) -> Hub | None:
    """Look a hub up by id ("st_louis") or display name ("St. Louis"), case-insensitively."""
    key = name_or_id.strip().lower()
    return _BY_KEY.get(key) or _BY_KEY.get(key.replace(" ", "_"))
