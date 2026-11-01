from fastapi import APIRouter
from app.api.v1.endpoints import (
    environmental,
    geospatial,
    health,
    incidents,
    intelligence,
    media,
    workflows,
)

api_router = APIRouter()

# Mount health liveness endpoint
api_router.include_router(health.router, tags=["Health"])

# Mount Incident Management endpoints
api_router.include_router(incidents.router, prefix="/incidents", tags=["Incidents"])

# Mount Media Ingestion endpoints
api_router.include_router(media.router, prefix="/media", tags=["Media"])

# Mount Geospatial Intelligence endpoints
api_router.include_router(geospatial.router, prefix="/geospatial", tags=["Geospatial"])

# Mount Environmental Data Integration endpoints
api_router.include_router(environmental.router, prefix="/environmental", tags=["Environmental"])

# Mount Multimodal Intelligence endpoints (Milestone 11)
api_router.include_router(intelligence.router, prefix="/intelligence", tags=["Intelligence"])

# Mount Multi-Agent Disaster Response Workflows (Milestone 12)
api_router.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
