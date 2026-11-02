import asyncio
import time

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_cache = {}
_request_lock = asyncio.Lock()
_last_request_at = 0.0


@router.get("/search", summary="Search for a location by name")
async def search_locations(
    q: str = Query(..., min_length=2, max_length=200)
):
    global _last_request_at

    query = " ".join(q.split())
    cache_key = query.casefold()

    if cache_key in _cache:
        return {"query": query, "results": _cache[cache_key]}

    async with _request_lock:
        if cache_key in _cache:
            return {"query": query, "results": _cache[cache_key]}

        wait = 1.0 - (time.monotonic() - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)

        try:
            async with httpx.AsyncClient(
                timeout=12.0,
                headers={"User-Agent": "ConvoyConnect/0.1 (location lookup)"}
            ) as client:
                _last_request_at = time.monotonic()
                response = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "limit": 5,
                        "addressdetails": 1,
                    },
                )
                response.raise_for_status()
                data = response.json()

        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=502,
                detail="Location search service is temporarily unavailable."
            ) from exc

        results = [
            {
                "display_name": item["display_name"],
                "latitude": float(item["lat"]),
                "longitude": float(item["lon"]),
            }
            for item in data
            if "lat" in item and "lon" in item and "display_name" in item
        ]

        if len(_cache) >= 500:
            _cache.clear()

        _cache[cache_key] = results

        return {"query": query, "results": results}
