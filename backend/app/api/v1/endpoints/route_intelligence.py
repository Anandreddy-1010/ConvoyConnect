from http.client import IncompleteRead

import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


import os
from dotenv import load_dotenv

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



def fetch_overpass_data(query):
    """Fetch nearby facility data using the configured Overpass API."""
    if not OVERPASS_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OVERPASS_API_KEY is missing from the backend .env file.",
        )

    overpass_url = (
        f"https://api.overpass.ch/v1/{OVERPASS_API_KEY}/interpreter"
    )

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
        with urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))

            if "remark" in data:
                raise HTTPException(
                    status_code=502,
                    detail=f"Overpass query warning: {data['remark']}",
                )

            return data

    except HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Overpass API returned HTTP {exc.code}. Please try again.",
        ) from exc

    except (IncompleteRead, URLError, TimeoutError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not retrieve nearby facilities: {type(exc).__name__}.",
        ) from exc


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

    query = (
        "[out:json][timeout:15];("
        f'node{tag_filter}(around:{radius_m},{latitude},{longitude});'
        f'way{tag_filter}(around:{radius_m},{latitude},{longitude});'
        ");out center tags;"
    )

    data = fetch_overpass_data(query)

    results = []
    seen = set()

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
            "name": tags.get("name") or {
    "fuel": "Petrol Pump",
    "restaurant": "Restaurant / Cafe",
    "repair": "Bike Repair Shop",
    "medical": "Medical Facility",
    "accommodation": "Room / Stay",
}.get(facility_type, "Unnamed facility"),
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

