# app/group_ai — Not implemented yet (Phase 3+)

Placeholder package for logic that combines NLP output
(`app/nlp`) and geospatial output (`app/geospatial`) into
group-level intelligence. Nothing here runs today.

## Planned scope

- **Group-state detection** (`state_detector.py`) — summarize the
  whole convoy's state (e.g. "tightly grouped", "spread out",
  "one rider separated") from individual rider statuses/positions.
- **Intelligent regrouping recommendation** — suggest a meeting point
  or pace adjustment when riders drift apart, based on geospatial
  output plus route data.
- Longer-term: combine this with chat NLP so a rider can ask
  "should we regroup?" and get an answer grounded in live positions.

## Why the stub file raises NotImplementedError

The class/method signature is defined now so the API layer could, in
principle, expose a "group summary" endpoint later without redesigning
this module's interface — but no endpoint calls it yet.
