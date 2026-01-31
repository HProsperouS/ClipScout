import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.api import routes_jobs

logger = logging.getLogger("uvicorn.access")

app = FastAPI(title="ClipScout API", version="0.1.0")


class LogRequestsMiddleware(BaseHTTPMiddleware):
    """Log when a request is received (before body is read), so long uploads show up immediately."""

    async def dispatch(self, request, call_next):
        method = request.method
        path = request.url.path
        logger.info("Request started: %s %s", method, path)
        response = await call_next(request)
        return response


app.add_middleware(LogRequestsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_jobs.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# When running in Docker, serve built frontend from /static
if Path("static").is_dir():
    static_path = Path("static")
    if (static_path / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

    @app.get("/")
    async def index():
        return FileResponse("static/index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not found")
        path = static_path / full_path
        if path.is_file():
            return FileResponse(path)
        return FileResponse("static/index.html")
