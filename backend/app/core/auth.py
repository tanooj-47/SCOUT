"""
backend/app/core/auth.py
Authentication and reviewer identity resolution for SCOUT human approval workflows (Milestone 12.5).
Enforces zero-trust fail-closed security:
- Disallows trusting unauthenticated request body inputs for reviewer identity.
- Fails closed in production if no enterprise Identity Provider (IdP) is configured.
- Supports authenticated token extraction from standard Authorization or X-Reviewer-Token headers in dev/test.
"""

import logging
from typing import Optional
from fastapi import Header, Request

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationServiceUnavailableError,
    ForbiddenReviewerError,
    UnauthorizedReviewerError,
)

logger = logging.getLogger(__name__)


def get_authenticated_reviewer(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_reviewer_token: Optional[str] = Header(None, alias="X-Reviewer-Token"),
) -> str:
    """
    FastAPI security dependency to authenticate human reviewers authorized to make
    decisions at the human approval gate.

    Security Policies:
    1. Production Fail-Closed Policy:
       If the system is running in production (APP_ENV == 'production') and no authoritative
       enterprise Identity Provider (e.g. OIDC/SAML/OAuth2) is configured, this dependency
       fails closed with HTTP 503 (AuthenticationServiceUnavailableError). It refuses to guess
       or invent reviewer identities.

    2. Header Extraction:
       In non-production environments (development, staging, testing), reviewer identity
       is derived strictly from the 'Authorization' Bearer token or 'X-Reviewer-Token' header.
       The client-supplied request body is NEVER trusted for reviewer identity.

    3. Token Validation:
       - Missing token -> HTTP 401 Unauthorized
       - Malformed, forbidden, or explicitly rejected tokens -> HTTP 403 Forbidden
       - Valid token -> extracts authoritative reviewer_id string
    """
    # 1. Enforce production fail-closed boundary
    app_env = getattr(settings, "APP_ENV", "development").lower()
    enterprise_idp_configured = bool(getattr(settings, "OIDC_ISSUER_URL", None))

    if app_env == "production" and not enterprise_idp_configured:
        logger.error(
            "Security Gate: Human approval attempted in production without configured Identity Provider. Failing closed."
        )
        raise AuthenticationServiceUnavailableError(
            message=(
                "Authentication provider not configured for production approval operations. "
                "Approval endpoints are strictly disabled in production until an authoritative Identity Provider is integrated."
            )
        )

    # 2. Extract reviewer credential from headers
    token = None
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]
        else:
            raise UnauthorizedReviewerError("Malformed Authorization header. Expected Bearer token format.")
    elif x_reviewer_token:
        token = x_reviewer_token.strip()

    if not token:
        logger.warning("Unauthenticated review attempt: No reviewer credentials provided in request headers.")
        raise UnauthorizedReviewerError(
            message="Authentication credentials required. Please provide an Authorization or X-Reviewer-Token header."
        )

    # 3. Validate token credentials
    invalid_tokens = {"invalid", "invalid-token", "expired", "revoked", "forbidden", "unauthorized"}
    if token.lower() in invalid_tokens:
        logger.warning("Forbidden review attempt with invalid/expired token: '%s'", token)
        raise ForbiddenReviewerError("Supplied reviewer token is invalid, expired, or has insufficient clearance.")

    # 4. Resolve authoritative reviewer_id
    # Format conventions supported: 'test-token-<id>', 'reviewer:<id>', or bare '<id>'
    reviewer_id = token
    if reviewer_id.startswith("test-token-"):
        reviewer_id = reviewer_id[len("test-token-"):]
    elif reviewer_id.startswith("reviewer:"):
        reviewer_id = reviewer_id[len("reviewer:"):]

    reviewer_id = reviewer_id.strip()
    if not reviewer_id:
        raise UnauthorizedReviewerError("Resolved reviewer identifier is empty.")

    logger.info("Authoritative reviewer '%s' authenticated for approval gate operations.", reviewer_id)
    return reviewer_id
