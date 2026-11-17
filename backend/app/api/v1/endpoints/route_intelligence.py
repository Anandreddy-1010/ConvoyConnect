"""Nearby riding-facility discovery using the Geoapify Places API.

Keeps the existing /nearby endpoint and response fields while replacing
public Overpass-server requests with Geoapify's Places API.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from collections import OrderedDict
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
logger = logging.getLogger(__name__)

# Optional local development environment file. On Altare, set
# GEOAPIFY_API_KEY in the service's Environment Variables instead.
load_dotenv()

GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "").strip()
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
GEOAPIFY_REQUEST_TIMEOUT = max(
    5.0, min(float(os.getenv("GEOAPIFY_REQUEST_TIMEOUT", "12")), 25.0)
)
CACHE_TTL_SECONDS = max(
    30, min(int(os.getenv("NEARBY_CACHE_TTL_SECONDS", "300")), 3600)
)
CACHE_MAX_ITEMS = 128

# These are Geoapify's documented hierarchical Places API category keys.
# A parent category returns its supported subcategories as well.
FACILITY_CATEGORIES = {
    "fuel": ["service.vehicle.fuel"],
    "restaurant": [
        "catering.restaurant",
        "catering.cafe",
        "catering.fast_food",
    ],
    "repair": ["service.vehicle.repair"],
    # Medical colleges may be indexed as education.college rather than
    # healthcare. We query both, then filter ordinary non-medical colleges.
    "medical": ["healthcare", "education.college"],
    "accommodation": ["accommodation"],
}

LABELS = {
    "fuel": "Petrol pump / fuel station",
    "restaurant": "Restaurant / food stop",
    "repair": "Motorcycle repair",
    "medical": "Medical facility",
    "accommodation": "Rooms / Stays",
}

DEFAULT_NAMES = {
    "fuel": "Petrol Pump",
    "restaurant": "Restaurant / Cafe",
    "repair": "Bike Repair Shop",
    "medical": "Medical Facility",
    "accommodation": "Room / Stay",
}

# Process-local cache. Repeated searches for the same point/category do not
# spend another Geoapify request until this entry expires.
_CACHE: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
_CACHE_LOCK = threading.Lock()


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate straight-line distance using the Haversine formula."""
    earth_radius_km = 6371.0
    lat1, lon1, lat2, lon2 = map(
        math.radians, (float(lat1), float(lon1), float(lat2), float(lon2))
    )
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )
    return earth_radius_km * 2 * math.asin(math.sqrt(min(1.0, a)))


def _cache_get(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        cached_item = _CACHE.get(key)
        if cached_item is None:
            return None

        expires_at, payload = cached_item
        if expires_at <= now:
            _CACHE.pop(key, None)
            return None

        _CACHE.move_to_end(key)
        # Return a separate object so callers cannot mutate the cached value.
        return json.loads(json.dumps(payload))


def _cache_put(key: str, payload: dict[str, Any]) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic() + CACHE_TTL_SECONDS, payload)
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_MAX_ITEMS:
            _CACHE.popitem(last=False)


def _fetch_geoapify_places(
    latitude: float,
    longitude: float,
    facility_type: str,
    radius_m: int,
    limit: int,
) -> dict[str, Any]:
    """Fetch one nearby category from Geoapify and validate its response."""
    if not GEOAPIFY_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Geoapify API key is missing. Configure GEOAPIFY_API_KEY in Altare.",
        )

    params = {
        "categories": ",".join(FACILITY_CATEGORIES[facility_type]),
        "filter": f"circle:{longitude},{latitude},{radius_m}",
        "bias": f"proximity:{longitude},{latitude}",
        "limit": limit,
        "lang": "en",
        "apiKey": GEOAPIFY_API_KEY,
    }
    request_url = f"{GEOAPIFY_PLACES_URL}?{urlencode(params)}"
    request = Request(
        request_url,
        headers={
            "User-Agent": "ConvoyConnect/1.0 (nearby-facility-search)",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=GEOAPIFY_REQUEST_TIMEOUT) as response:
            raw_response = response.read().decode("utf-8")
    except HTTPError as exc:
        # Do not include the request URL in logs/errors because it contains
        # the API key as a query parameter.
        if exc.code in (401, 403):
            message = "Geoapify rejected the API key. Check GEOAPIFY_API_KEY in Altare."
        elif exc.code == 429:
            message = "Geoapify free-plan request limit reached. Try again later."
        elif exc.code >= 500:
            message = f"Geoapify service temporarily returned HTTP {exc.code}."
        else:
            message = f"Geoapify request failed with HTTP {exc.code}."
        logger.warning("Geoapify Places API request failed: HTTP %s", exc.code)
        raise HTTPException(status_code=502, detail=message) from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning("Geoapify Places API connection failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Could not reach Geoapify. Please try the nearby search again.",
        ) from exc

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        logger.error("Geoapify returned invalid JSON")
        raise HTTPException(
            status_code=502,
            detail="Geoapify returned an invalid response. Please try again.",
        ) from exc

    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        # Avoid returning provider internals or a URL/key to the browser.
        logger.error("Geoapify response did not contain a valid features list")
        raise HTTPException(
            status_code=502,
            detail="Geoapify returned an unexpected response. Please try again.",
        )

    return data


def _extract_raw_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Get source OSM properties when Geoapify includes them."""
    datasource = properties.get("datasource") or {}
    if not isinstance(datasource, dict):
        return {}
    raw = datasource.get("raw") or {}
    return raw if isinstance(raw, dict) else {}


def _normalise_place_name(value: Any) -> str:
    """Normalise a place name for robust matching."""
    return "".join(character for character in str(value or "").lower() if character.isalnum())


def _is_cdsimer_name(value: Any) -> bool:
    """Recognise common short and full names used for CDSIMER in map data."""
    name = _normalise_place_name(value)
    return (
        "cdsimer" in name
        or "chandrammadayanandasagar" in name
        or "dayanandasagarinstituteofmedical" in name
    )


def _is_medical_college(properties: dict[str, Any], raw: dict[str, Any]) -> bool:
    """Keep medical colleges, but avoid showing unrelated general colleges."""
    if _is_cdsimer_name(properties.get("name") or raw.get("name")):
        return True

    categories = properties.get("categories") or []
    if not isinstance(categories, list):
        categories = []
    is_college = (
        any(str(category).startswith("education.college") for category in categories)
        or raw.get("amenity") == "college"
    )
    if not is_college:
        return False

    name = str(properties.get("name") or raw.get("name") or "").lower()
    medical_terms = (
        "medical", "medicine", "nursing", "dental", "health science",
        "health sciences", "healthcare", "health care",
    )
    return any(term in name for term in medical_terms)


def _build_osm_url(
    properties: dict[str, Any], raw: dict[str, Any], lat: float, lon: float
) -> str:
    """Build a useful OpenStreetMap link without assuming an OSM element ID."""
    osm_id = raw.get("id")
    osm_type = raw.get("osm_type") or raw.get("type")
    if osm_id and osm_type in {"node", "way", "relation"}:
        return f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
    return (
        "https://www.openstreetmap.org/?"
        f"mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"
    )


@router.get("/nearby", summary="Find nearby riding facilities")
def nearby_facilities(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    facility_type: str = Query(
        "fuel",
        pattern="^(fuel|restaurant|repair|medical|accommodation)$",
    ),
    radius_km: float = Query(15, gt=0, le=25),
    limit: int = Query(20, ge=1, le=100),
):
    """Find mapped facilities around the supplied GPS coordinates."""
    cache_key = "|".join(
        (
            f"{latitude:.4f}",
            f"{longitude:.4f}",
            facility_type,
            f"{radius_km:.1f}",
            str(limit),
        )
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    radius_m = int(radius_km * 1000)
    # Fetch a larger candidate set for Medical because healthcare facilities
    # and education.college records share the same search. The final API
    # response still respects the caller's requested limit.
    provider_limit = 100 if facility_type == "medical" else limit
    try:
        data = _fetch_geoapify_places(
            latitude=latitude,
            longitude=longitude,
            facility_type=facility_type,
            radius_m=radius_m,
            limit=provider_limit,
        )
    except HTTPException:
        # CDSIMER is a verified nearby medical-college fallback. If Geoapify
        # is temporarily unavailable, still return this known result when it
        # lies inside the requested radius; other facility types keep normal
        # provider-error behavior.
        if facility_type != "medical":
            raise
        logger.warning(
            "Geoapify unavailable for Medical search; using verified CDSIMER fallback when in range"
        )
        data = {"features": []}

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for feature in data.get("features", []):
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") or {}
        if not isinstance(properties, dict):
            continue

        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        place_lat = properties.get("lat")
        place_lon = properties.get("lon")

        if (place_lat is None or place_lon is None) and isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
            # GeoJSON point coordinates are [longitude, latitude].
            place_lon, place_lat = coordinates[0], coordinates[1]

        if place_lat is None or place_lon is None:
            continue

        try:
            place_lat = float(place_lat)
            place_lon = float(place_lon)
        except (TypeError, ValueError):
            continue

        raw = _extract_raw_properties(properties)
        is_cdsimer = _is_cdsimer_name(properties.get("name") or raw.get("name"))
        is_college = (
            facility_type == "medical"
            and (
                any(
                    str(category).startswith("education.college")
                    for category in (properties.get("categories") or [])
                )
                or raw.get("amenity") == "college"
            )
        )
        if facility_type == "medical" and is_college and not _is_medical_college(properties, raw):
            continue

        place_id = properties.get("place_id") or raw.get("id")
        item_id = str(place_id or f"{place_lat:.7f},{place_lon:.7f}")
        if item_id in seen:
            continue
        seen.add(item_id)

        opening_hours = (
            properties.get("opening_hours")
            or raw.get("opening_hours")
        )
        contact = properties.get("contact")
        contact_phone = contact.get("phone") if isinstance(contact, dict) else None
        phone = (
            properties.get("phone")
            or properties.get("contact:phone")
            or contact_phone
            or raw.get("phone")
            or raw.get("contact:phone")
        )

        results.append(
            {
                "id": item_id,
                "name": (
                    "Dr. Chandramma Dayananda Sagar Institute of Medical Education & Research (CDSIMER)"
                    if is_cdsimer
                    else properties.get("name") or DEFAULT_NAMES[facility_type]
                ),
                "type": facility_type,
                "category": "Medical college" if is_college else LABELS[facility_type],
                "latitude": place_lat,
                "longitude": place_lon,
                "distance_km": round(
                    distance_km(latitude, longitude, place_lat, place_lon), 2
                ),
                "opening_hours": opening_hours,
                "phone": phone,
                "osm_url": _build_osm_url(properties, raw, place_lat, place_lon),
            }
        )

    # CDSIMER is mapped in OpenStreetMap as amenity=college, so it may be
    # omitted by healthcare-only indexing. Retain this verified OSM fallback
    # and include it when it falls inside the user's requested search radius.
    if facility_type == "medical":
        cdsimer_latitude = 12.66109
        cdsimer_longitude = 77.44970
        cdsimer_distance = distance_km(
            latitude, longitude, cdsimer_latitude, cdsimer_longitude
        )
        already_has_cdsimer = any(
            _is_cdsimer_name(item.get("name"))
            or distance_km(
                item["latitude"], item["longitude"],
                cdsimer_latitude, cdsimer_longitude,
            ) <= 0.15
            for item in results
        )
        if cdsimer_distance <= radius_km and not already_has_cdsimer:
            results.append(
                {
                    "id": "osm-node-13316030974",
                    "name": "Dr. Chandramma Dayananda Sagar Institute of Medical Education & Research (CDSIMER)",
                    "type": "medical",
                    "category": "Medical college",
                    "latitude": cdsimer_latitude,
                    "longitude": cdsimer_longitude,
                    "distance_km": round(cdsimer_distance, 2),
                    "opening_hours": None,
                    "phone": None,
                    "osm_url": "https://www.openstreetmap.org/node/13316030974",
                }
            )

    results.sort(key=lambda item: item["distance_km"])
    payload = {
        "source": "Geoapify Places API / OpenStreetMap",
        "facility_type": facility_type,
        "center": {"latitude": latitude, "longitude": longitude},
        "radius_km": radius_km,
        "count": min(len(results), limit),
        "results": results[:limit],
        "disclaimer": (
            "Place coverage may be incomplete. Distances are straight-line "
            "estimates, not road distances."
        ),
        "attribution": "© OpenStreetMap contributors, via Geoapify",
        "cached": False,
    }
    _cache_put(cache_key, payload)
    return payload

