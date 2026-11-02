from fastapi import APIRouter

from app.api.v1.endpoints import (
    chat,
    geocoding,
    health,
    locations,
    nlp,
    push,
    rides,
    riders,
    route_intelligence,
    sos,
)	
api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(rides.router, prefix="/rides", tags=["Rides"])
api_router.include_router(riders.router, prefix="/rides", tags=["Riders"])
api_router.include_router(locations.router, prefix="/rides", tags=["Locations"])
api_router.include_router(chat.router, prefix="/rides", tags=["Chat"])
api_router.include_router(nlp.router, prefix="/nlp", tags=["NLP"])

api_router.include_router(
    route_intelligence.router,
    prefix="/route-intelligence",
    tags=["Route Intelligence"],
)
api_router.include_router(
    geocoding.router,
    prefix="/geocoding",
    tags=["Geocoding"],
)
api_router.include_router(sos.router, prefix="/sos", tags=["SOS"])
api_router.include_router(push.router, prefix="/push", tags=["Push Notifications"])

