"""Nearby riding-facility discovery backed by OpenStreetMap Overpass.

Keeps the existing /nearby API response contract while adding parallel
provider fallback, bounded request timeouts, and a short in-process cache.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
logger = logging.getLogger(__name__)

# Optional local file for development. On Altare, configure variables in the
# deployment environment; do not commit overpass.env or API credentials.
load_dotenv("overpass.env")

OVERPASS_API_KEY = os.getenv("OVERPASS_API_KEY", "").strip()

_DEFAULT_OVERPASS_URLS = [
    # VK Maps global Overpass instance; currently listed as an available
    # global-data provider by the OpenStreetMap wiki.
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def _get_overpass_urls() -> list[str]:
    """Build the provider list, allowing deployment-time overrides."""
    configured = os.getenv("OVERPASS_API_URLS") or os.getenv("OVERPASS_URLS")
    urls: list[str] = []

    if configured:
        urls.extend(url.strip() for url in configured.split(",") if url.strip())

    # Retain support for the optional keyed Overpass.ch endpoint.
    if OVERPASS_API_KEY:
        urls.append(f"https://api.overpass.ch/v1/{OVERPASS_API_KEY}/interpreter")

    urls.extend(_DEFAULT_OVERPASS_URLS)

    # Preserve order and remove duplicates.
    return list(dict.fromkeys(urls))


OVERPASS_URLS = _get_overpass_urls()
# VK Maps has historically taken around 13-17 seconds for some queries,
# so allow enough time for that fallback while keeping the request bounded.
OVERPASS_REQUEST_TIMEOUT = max(
    5.0, min(float(os.getenv("OVERPASS_REQUEST_TIMEOUT", "18")), 20.0)
)
OVERPASS_CACHE_TTL_SECONDS = max(
    30, min(int(os.getenv("OVERPASS_CACHE_TTL_SECONDS", "300")), 3600)
)
OVERPASS_CACHE_MAX_ITEMS = 128

# Small process-local TTL cache. It avoids repeated Overpass calls for the
# same GPS point/category while keeping stale data bounded in time.
_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_CACHE_LOCK = threading.Lock()

FACILITY_FILTERS = {
    "fuel": '["amenity"="fuel"]',
    "restaurant": '["amenity"~"restaurant|cafe|fast_food"]',
    "repair": '["shop"~"motorcycle|motorcycle_repair|car_repair|tyres|bicycle|vehicle"]',
    "medical": '["amenity"~"hospital|clinic|doctors|pharmacy"]',
    "accommodation": '["tourism"~"hotel|guest_house|motel|hostel|resort"]',
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


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate straight-line distance using the Haversine formula."""
    radius = 6371.0
    lat1, lon1, lat2, lon2 = map(
        math.radians, (float(lat1), float(lon1), float(lat2), float(lon2))
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(min(1.0, a)))


def _cache_get(key: str) -> dict | None:
    now = time.monotonic()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if expires_at <= now:
            _CACHE.pop(key, None)
            return None
        _CACHE.move_to_end(key)
        # JSON round-trip gives the caller an independent copy.
        return json.loads(json.dumps(payload))


def _cache_put(key: str, payload: dict) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic() + OVERPASS_CACHE_TTL_SECONDS, payload)
        _CACHE.move_to_end(key)
        while len(_CACHE) > OVERPASS_CACHE_MAX_ITEMS:
            _CACHE.popitem(last=False)


def _request_overpass(overpass_url: str, query: str) -> dict:
    """Make and validate one Overpass request."""
    request = Request(
        overpass_url,
        data=urlencode({"data": query}).encode("utf-8"),
        headers={
            "User-Agent": "ConvoyConnect/1.0 (nearby-facility-search)",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    with urlopen(request, timeout=OVERPASS_REQUEST_TIMEOUT) as response:
        raw = response.read().decode("utf-8")

    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Overpass returned a non-object JSON response")
    if data.get("remark"):
        raise RuntimeError(str(data["remark"])[:240])
    if not isinstance(data.get("elements", []), list):
        raise ValueError("Overpass response has an invalid elements field")

    return data


def fetch_overpass_data(query: str) -> dict:
    """Query providers concurrently and return the first valid response.

    All providers are started together. A slow/unavailable provider therefore
    does not make the user wait for every provider one after another.
    """
    urls = _get_overpass_urls()
    if not urls:
        raise HTTPException(
            status_code=503,
            detail="Nearby facility providers are not configured.",
        )

    failures: list[str] = []
    executor = ThreadPoolExecutor(max_workers=min(len(urls), 8))
    future_to_url = {
        executor.submit(_request_overpass, overpass_url, query): overpass_url
        for overpass_url in urls
    }
    pending = set(future_to_url)

    # The per-request socket timeout is the main bound. This overall deadline
    # prevents waiting indefinitely if a provider behaves unexpectedly.
    deadline = time.monotonic() + OVERPASS_REQUEST_TIMEOUT + 1.5

    try:
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            completed, pending = wait(
                pending,
                timeout=remaining,
                return_when=FIRST_COMPLETED,
            )
            if not completed:
                break

            for future in completed:
                overpass_url = future_to_url[future]
                try:
                    data = future.result()
                    logger.info(
                        "Nearby facilities fetched from Overpass provider %s",
                        overpass_url,
                    )
                    return data
                except HTTPError as exc:
                    message = f"HTTP {exc.code}"
                except (
                    IncompleteRead,
                    URLError,
                    TimeoutError,
                    OSError,
                    ValueError,
                    RuntimeError,
                ) as exc:
                    message = f"{type(exc).__name__}: {exc}"
                except Exception as exc:
                    message = f"{type(exc).__name__}: {exc}"

                failures.append(f"{overpass_url}: {message}")
                logger.warning("Overpass provider failed: %s", failures[-1])

    finally:
        # Do not wait for a slow provider after another provider has succeeded
        # or the overall deadline has expired.
        executor.shutdown(wait=False, cancel_futures=True)

    for future in pending:
        overpass_url = future_to_url[future]
        if future.cancel():
            failures.append(f"{overpass_url}: cancelled after request deadline")
        else:
            failures.append(f"{overpass_url}: request did not finish before deadline")

    logger.error("All Overpass providers failed: %s", " | ".join(failures))
    raise HTTPException(
        status_code=503,
        detail=(
            "Nearby facility data is temporarily unavailable from OpenStreetMap. "
            "Please try again shortly."
        ),
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
    # Round coordinates for cache matching while retaining the original
    # coordinates in the response. ~11 m precision is sufficient for caching.
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

    tag_filter = FACILITY_FILTERS[facility_type]
    radius_m = int(radius_km * 1000)
    query_timeout = max(10, min(int(OVERPASS_REQUEST_TIMEOUT * 2), 25))
    query = (
        f"[out:json][timeout:{query_timeout}];("
        f'node{tag_filter}(around:{radius_m},{latitude},{longitude});'
        f'way{tag_filter}(around:{radius_m},{latitude},{longitude});'
        ");out center tags;"
    )

    data = fetch_overpass_data(query)
    results: list[dict] = []
    seen: set[str] = set()

    for element in data.get("elements", []):
        tags = element.get("tags", {}) or {}
        lat = element.get("lat")
        lon = element.get("lon")

        if lat is None or lon is None:
            center = element.get("center", {}) or {}
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            continue

        element_id = f"{element.get('type')}/{element.get('id')}"
        if element_id in seen:
            continue
        seen.add(element_id)

        lat = float(lat)
        lon = float(lon)
        results.append(
            {
                "id": element_id,
                "name": tags.get("name") or DEFAULT_NAMES.get(
                    facility_type, "Unnamed facility"
                ),
                "type": facility_type,
                "category": LABELS[facility_type],
                "latitude": lat,
                "longitude": lon,
                "distance_km": round(
                    distance_km(latitude, longitude, lat, lon), 2
                ),
                "opening_hours": tags.get("opening_hours"),
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "osm_url": f"https://www.openstreetmap.org/{element_id}",
            }
        )

    results.sort(key=lambda item: item["distance_km"])
    payload = {
        "source": "OpenStreetMap",
        "facility_type": facility_type,
        "center": {"latitude": latitude, "longitude": longitude},
        "radius_km": radius_km,
        "count": min(len(results), limit),
        "results": results[:limit],
        "disclaimer": (
            "OpenStreetMap coverage may be incomplete. Distances are "
            "straight-line estimates, not road distances."
        ),
        "cached": False,
    }
    _cache_put(cache_key, payload)
    return payload
