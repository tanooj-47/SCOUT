from fastapi import APIRouter
from app.api.v1.endpoints import health

api_router = APIRouter()

# Mount health liveness endpoint
api_router.include_router(health.router, tags=["Health"])
