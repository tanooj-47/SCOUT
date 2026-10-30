from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging

# Configure logging on module load
setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="SCOUT — Smart Crisis Observation & Understanding Technology API",
    version="0.1.0",
    debug=settings.DEBUG,
)

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


@app.get("/", tags=["Root"])
def read_root():
    """
    Root informational endpoint providing quick navigation links.
    """
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "docs_url": "/docs",
        "health_endpoint": f"{settings.API_V1_STR}/health",
    }
