from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import PROJECT_ROOT, settings
from app.core.exceptions import (
    SCOUTException,
    http_exception_handler,
    scout_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import setup_logging

# Configure logging on module load
setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="SCOUT — Smart Crisis Observation & Understanding Technology API",
    version="0.1.0",
    debug=settings.DEBUG,
)

# Register custom exception handlers for uniform error envelopes
app.add_exception_handler(SCOUTException, scout_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Configure Cross-Origin Resource Sharing (CORS)
if settings.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API v1 router under the configured prefix
app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount frontend dashboard static files if directory exists
frontend_dir = PROJECT_ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.get("/", tags=["Root"])
def read_root():
    """
    Root informational endpoint providing quick navigation links.
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "docs_url": "/docs",
        "health_endpoint": f"{settings.API_V1_STR}/health",
        "geospatial_dashboard": "/dashboard",
    }
