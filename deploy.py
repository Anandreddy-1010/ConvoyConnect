
import os
import sys
from pathlib import Path

import uvicorn
from fastapi.responses import FileResponse

# Import the existing backend without modifying it
ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
DIST_DIR = ROOT / "frontend" / "dist"

sys.path.insert(0, str(BACKEND_DIR))

from app.main import app

# Verify that the frontend production build exists
if not (DIST_DIR / "index.html").is_file():
    raise RuntimeError("Frontend build not found: frontend/dist/index.html")

# Remove the existing JSON root route only from this deployment instance
app.router.routes = [
    route for route in app.router.routes
    if not (
        getattr(route, "path", None) == "/"
        and "GET" in getattr(route, "methods", set())
    )
]

# Serve React frontend and its assets
async def serve_frontend(path: str = ""):
    requested = (DIST_DIR / path).resolve()
    base = DIST_DIR.resolve()

    if requested.is_relative_to(base) and requested.is_file():
        return FileResponse(requested)

    return FileResponse(DIST_DIR / "index.html")


app.add_api_route(
    "/",
    serve_frontend,
    methods=["GET"],
    include_in_schema=False,
)

app.add_api_route(
    "/{path:path}",
    serve_frontend,
    methods=["GET"],
    include_in_schema=False,
)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
