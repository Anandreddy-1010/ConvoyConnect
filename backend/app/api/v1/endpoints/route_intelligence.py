
import json
import math
import os
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    wait,
    FIRST_COMPLETED,
)
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from http.client import IncompleteRead
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query


router = APIRouter()

load_dotenv("overpass.env")

OVERPASS_API_KEY = os.getenv("OVERPASS_API_KEY")

OVERPASS_URLS = (
    [f"https://api.overpass.ch/v1/{OVERPASS_API_KEY}/interpreter"]
    if OVERPASS_API_KEY
    else [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
    ]
)

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

# Cache successful Overpass responses for two minutes.
CACHE_TTL = 120
_facility_cache = {}
_cache_lock = Lock()


def distance_km(lat1, lon1, lat2, lon2):
    """Calculate straight-line distance using the Haversine formula."""

    radius = 6371.0

    lat1, lon1, lat2, lon2 = map(
        math.radians, (lat1, lon1, lat2, lon2)
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return radius * 2 * math.asin(math.sqrt(min(1.0, a)))


def fetch_from_server(overpass_url, query):
    """Fetch data from one Overpass server."""

    request = Request(
        overpass_url,
        data=urlencode({"data": query}).encode("utf-8"),
        headers={
            "User-Agent": "ConvoyConnect/1.0",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=12) as response:
            data = json.loads(response.read().decode("utf-8"))

        if "remark" in data:
            raise RuntimeError(data["remark"])

        return data

    except HTTPError as exc:
        try:
            body = exc.read().decode(
                "utf-8", errors="replace"
            )[:200]
        except Exception:
            body = "No response body"

        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

    except (
        IncompleteRead,
        URLError,
        TimeoutError,
        OSError,
        ValueError,
    ) as exc:
        raise RuntimeError(
            f"{type(exc).__name__}: {exc}"
        ) from exc


def fetch_overpass_data(query, cache_key):
    """Fetch from multiple Overpass servers simultaneously."""

    now = time.monotonic()

    with _cache_lock:
        cached = _facility_cache.get(cache_key)

        if cached and now - cached["time"] < CACHE_TTL:
            print("Nearby facilities: cache hit")
            return cached["data"]

        if cached:
            _facility_cache.pop(cache_key, None)

    if not OVERPASS_URLS:
        raise HTTPException(
            status_code=502,
            detail="No Overpass API endpoints are configured.",
        )

    executor = ThreadPoolExecutor(
        max_workers=len(OVERPASS_URLS)
    )

    futures = {
        executor.submit(fetch_from_server, url, query): url
        for url in OVERPASS_URLS
    }

    pending = set(futures)
    errors = []

    try:
        deadline = time.monotonic() + 14

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
                server = futures[future]

                try:
                    data = future.result()

                    with _cache_lock:
                        _facility_cache[cache_key] = {
                            "time": time.monotonic(),
                            "data": data,
                        }

                    print(
                        f"Nearby facilities: successful server {server}"
                    )

                    return data

                except Exception as exc:
                    error = f"{server}: {exc}"
                    errors.append(error)
                    print(f"Overpass failed: {error}")

    finally:
        executor.shutdown(
            wait=False,
            cancel_futures=True,
        )

    last_error = (
        "; ".join(errors[-3:])
        if errors
        else "All Overpass servers timed out."
    )

    raise HTTPException(
        status_code=502,
        detail=f"Nearby facilities unavailable: {last_error}",
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

    tag_filter = FACILITY_FILTERS[facility_type]
    radius_m = int(radius_km * 1000)

    # Normalize coordinates so nearby GPS updates can reuse cached data.
    search_latitude = round(latitude, 3)
    search_longitude = round(longitude, 3)

    cache_key = (
        search_latitude,
        search_longitude,
        facility_type,
        radius_m,
    )

    query = (
        "[out:json][timeout:10];("
        f'node{tag_filter}(around:{radius_m},{search_latitude},{search_longitude});'
        f'way{tag_filter}(around:{radius_m},{search_latitude},{search_longitude});'
        ");out center tags;"
    )

    data = fetch_overpass_data(query, cache_key)

    results = []
    seen = set()

    default_names = {
        "fuel": "Petrol Pump",
        "restaurant": "Restaurant / Cafe",
        "repair": "Bike Repair Shop",
        "medical": "Medical Facility",
        "accommodation": "Room / Stay",
    }

    for element in data.get("elements", []):

        tags = element.get("tags", {})

        lat = element.get("lat")
        lon = element.get("lon")

        if lat is None or lon is None:
            center = element.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            continue

        element_id = f"{element.get('type')}/{element.get('id')}"

        if element_id in seen:
            continue

        seen.add(element_id)

        results.append({
            "id": element_id,
            "name": tags.get("name") or default_names.get(
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
            "osm_url": (
                f"https://www.openstreetmap.org/{element_id}"
            ),
        })

    results.sort(key=lambda item: item["distance_km"])

    return {
        "source": "OpenStreetMap",
        "facility_type": facility_type,
        "center": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "radius_km": radius_km,
        "count": min(len(results), limit),
        "results": results[:limit],
        "disclaimer": (
            "OpenStreetMap coverage may be incomplete. Distances are "
            "straight-line estimates, not road distances."
        ),
    }
