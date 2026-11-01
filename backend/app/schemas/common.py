from typing import Generic, List, TypeVar, Optional, Dict, Any
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""
    limit: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")
    offset: int = Field(default=0, ge=0, description="Number of items to skip")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard generic pagination envelope."""
    items: List[T]
    total: int = Field(..., ge=0, description="Total matching items count")
    limit: int = Field(..., ge=1, description="Page size limit applied")
    offset: int = Field(..., ge=0, description="Page offset applied")
    has_next: bool = Field(..., description="Whether subsequent items exist")
    has_prev: bool = Field(..., description="Whether preceding items exist")


class ErrorDetail(BaseModel):
    """Standard structured error detail."""
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional context or validation details")


class ErrorResponse(BaseModel):
    """Uniform top-level error response envelope."""
    error: ErrorDetail
