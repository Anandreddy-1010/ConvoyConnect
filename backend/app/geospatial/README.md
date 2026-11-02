# app/geospatial — Not implemented yet (Phase 3)

Placeholder package. No distance/trajectory math runs anywhere in the
API today — `GET /rides/{ride_id}/locations` just echoes back whatever
coordinates were last submitted per rider, with no computed
distances.

## Planned scope

- **Haversine distance** (`distance.py`) — great-circle distance
  between two GPS points; the basis for "how far is this rider from
  the group" calculations.
- **Separation detection** (`separation_detector.py`) — given the
  group's positions, flag riders whose distance from the group
  centroid (or from the route line) exceeds a threshold.
- **Trajectory processing** — smoothing/interpolating a rider's
  location history (once location *history*, not just latest position,
  is persisted) to reduce GPS noise before feeding into detection.
- **Delay prediction** — estimate ETA drift from a rider's speed
  trend versus the group's average pace.

## Why the stub files raise NotImplementedError

Function signatures are defined now so `app/services/location_service.py`
and, later, `app/group_ai` can be written against a stable interface,
without any placeholder math silently producing misleading numbers.
