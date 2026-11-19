"""Client for the FEMA National Risk Index county layer (public ArcGIS REST service, no key).

We use the `*_AFREQ` fields: annualized frequency, i.e. expected hazard events per year. We do NOT use
`*_RISKS`, because it multiplies the hazard by the value exposed in the county, so every large-city
county scores ~99 on almost everything and our hubs can't be told apart.
"""

import httpx

NRI_COUNTIES_URL = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/"
    "National_Risk_Index_Counties/FeatureServer/0/query"
)

# The FEMA fields we store. Which hazard each one feeds is defined in scoring.py.
NRI_FIELDS = (
    "WNTW_AFREQ",  # winter weather
    "ISTM_AFREQ",  # ice storm
    "CWAV_AFREQ",  # cold wave
    "HRCN_AFREQ",  # hurricane
    "IFLD_AFREQ",  # riverine (inland) flooding
    "CFLD_AFREQ",  # coastal flooding
    "HWAV_AFREQ",  # heat wave
    "TRND_AFREQ",  # tornado
    "HAIL_AFREQ",  # hail
    "SWND_AFREQ",  # strong wind
)


def fetch_counties(county_fips: list[str]) -> dict[str, dict[str, float | None]]:
    """Fetch NRI fields for the given 5-digit county FIPS codes. Returns {fips: {field: value}}."""
    in_list = ",".join(f"'{fips}'" for fips in county_fips if fips.isdigit())
    params = {
        "where": f"STCOFIPS IN ({in_list})",
        "outFields": ",".join(("STCOFIPS",) + NRI_FIELDS),
        "returnGeometry": "false",
        "f": "json",
    }
    resp = httpx.get(NRI_COUNTIES_URL, params=params, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:  # ArcGIS reports errors with HTTP 200
        raise RuntimeError(f"FEMA NRI query failed: {body['error']}")
    return {
        feat["attributes"]["STCOFIPS"]: {field: feat["attributes"].get(field) for field in NRI_FIELDS}
        for feat in body["features"]
    }
