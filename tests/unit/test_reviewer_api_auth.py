"""Tests for reviewer API token authentication and identity binding."""
import json

import pytest

from src.web.reviewer_auth import (
    ReviewerAuthConfigurationError,
    ReviewerAuthDisabled,
    ReviewerAuthenticationError,
    reviewer_id_for_token,
)


def test_reviewer_token_maps_to_server_configured_identity():
    token = "test-only-high-entropy-token"
    configured = json.dumps({"analyst_1": token, "senior_reviewer": "another-token"})
    assert reviewer_id_for_token(token, configured) == "analyst_1"


def test_reviewer_token_rejects_unknown_token():
    with pytest.raises(ReviewerAuthenticationError):
        reviewer_id_for_token("wrong-token", json.dumps({"analyst_1": "expected-token"}))


def test_reviewer_token_api_is_disabled_without_configuration():
    with pytest.raises(ReviewerAuthDisabled):
        reviewer_id_for_token("any-token", "")


@pytest.mark.parametrize("configured", ["not-json", "[]", "null", ""])
def test_reviewer_token_configuration_must_be_a_json_object(configured):
    if configured == "":
        expected = ReviewerAuthDisabled
    else:
        expected = ReviewerAuthConfigurationError
    with pytest.raises(expected):
        reviewer_id_for_token("any-token", configured)


def test_reviewer_identity_is_not_accepted_from_untrusted_payload():
    configured = json.dumps({"trusted_reviewer": "trusted-secret"})
    with pytest.raises(ReviewerAuthenticationError):
        reviewer_id_for_token("attacker-supplied-reviewer-id", configured)


@pytest.mark.asyncio
async def test_fastapi_reviewer_dependency_binds_identity_and_fails_closed(monkeypatch):
    from fastapi import HTTPException
    from src.common.config import settings
    from src.web.app import app, require_reviewer

    monkeypatch.setattr(settings, "reviewer_api_tokens", json.dumps({"lead_analyst": "server-secret"}))
    assert await require_reviewer("server-secret") == "lead_analyst"

    with pytest.raises(HTTPException) as invalid:
        await require_reviewer("wrong-secret")
    assert invalid.value.status_code == 401

    monkeypatch.setattr(settings, "reviewer_api_tokens", "")
    with pytest.raises(HTTPException) as disabled:
        await require_reviewer("any-secret")
    assert disabled.value.status_code == 503

    route_paths = {route.path for route in app.routes}
    assert "/api/ipos/{symbol}/facts/pending" in route_paths
    assert "/api/facts/{fact_id}/review" in route_paths
