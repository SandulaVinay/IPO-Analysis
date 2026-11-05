"""Authentication helpers for reviewer-only API operations.

Tokens are configured as a JSON object mapping reviewer IDs to high-entropy
secrets. The caller never supplies the reviewer identity in the request body.
"""
from __future__ import annotations

import json
import secrets
from typing import Dict


class ReviewerAuthError(Exception):
    """Base error for reviewer API authentication."""


class ReviewerAuthDisabled(ReviewerAuthError):
    """Raised when no reviewer tokens are configured."""


class ReviewerAuthConfigurationError(ReviewerAuthError):
    """Raised when reviewer token configuration is invalid."""


class ReviewerAuthenticationError(ReviewerAuthError):
    """Raised when a supplied token does not match a configured reviewer."""


def reviewer_id_for_token(presented_token: str, configured_tokens: str) -> str:
    """Return the configured reviewer ID for a valid token using constant-time comparison."""
    if not configured_tokens or not configured_tokens.strip():
        raise ReviewerAuthDisabled("Reviewer API authentication is not configured.")

    try:
        token_map = json.loads(configured_tokens)
    except (TypeError, ValueError) as exc:
        raise ReviewerAuthConfigurationError("Reviewer token configuration must be valid JSON.") from exc

    if not isinstance(token_map, dict) or not token_map:
        raise ReviewerAuthConfigurationError("Reviewer token configuration must be a non-empty JSON object.")

    if not isinstance(presented_token, str) or not presented_token:
        raise ReviewerAuthenticationError("A valid reviewer token is required.")

    for reviewer_id, expected_token in token_map.items():
        if not isinstance(reviewer_id, str) or not reviewer_id.strip():
            continue
        if not isinstance(expected_token, str) or not expected_token:
            continue
        if secrets.compare_digest(presented_token, expected_token):
            return reviewer_id.strip()

    raise ReviewerAuthenticationError("Invalid reviewer token.")
