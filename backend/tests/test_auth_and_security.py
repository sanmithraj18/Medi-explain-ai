"""
Unit tests for MediExplain AI Phase 1 — Authentication & Security dependencies.
Verifies token extraction, user authentication, role checks, and email verification.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from app.core.security import extract_bearer_token, verify_supabase_token
from app.core.dependencies import (
    get_current_user,
    require_email_verified,
    require_admin,
    require_active_subscription,
)
from app.db.supabase_client import get_supabase


def test_extract_bearer_token_success():
    header = "Bearer my_secret_token_123"
    token = extract_bearer_token(header)
    assert token == "my_secret_token_123"


def test_extract_bearer_token_missing():
    with pytest.raises(HTTPException) as exc:
        extract_bearer_token(None)
    assert exc.value.status_code == 401
    assert "Missing or malformed" in exc.value.detail


def test_extract_bearer_token_malformed():
    with pytest.raises(HTTPException) as exc:
        extract_bearer_token("Basic dXNlcjpwYXNz")
    assert exc.value.status_code == 401


def test_extract_bearer_token_empty():
    with pytest.raises(HTTPException) as exc:
        extract_bearer_token("Bearer ")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_supabase_token_success():
    mock_supabase = MagicMock()
    mock_user = MagicMock()
    mock_user.id = "user-123"
    mock_user.email = "patient@example.com"
    mock_user.email_confirmed_at = "2026-01-01T00:00:00Z"
    
    mock_response = MagicMock()
    mock_response.user = mock_user
    mock_supabase.auth.get_user.return_value = mock_response

    user = await verify_supabase_token("valid_token", mock_supabase)
    assert user["id"] == "user-123"
    assert user["email"] == "patient@example.com"
    assert user["email_confirmed"] is True


@pytest.mark.asyncio
async def test_verify_supabase_token_invalid():
    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("Invalid token")

    with pytest.raises(HTTPException) as exc:
        await verify_supabase_token("invalid_token", mock_supabase)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_email_verified_passes():
    user = {"id": "1", "email": "test@test.com", "email_confirmed": True}
    res = await require_email_verified(user)
    assert res == user


@pytest.mark.asyncio
async def test_require_email_verified_fails():
    user = {"id": "1", "email": "test@test.com", "email_confirmed": False}
    with pytest.raises(HTTPException) as exc:
        await require_email_verified(user)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_passes():
    user = {"id": "admin-1", "email_confirmed": True}
    mock_supabase = MagicMock()
    mock_query = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "is_admin": True
    }
    
    res = await require_admin(user, mock_supabase)
    assert res == user


@pytest.mark.asyncio
async def test_require_admin_forbidden():
    user = {"id": "normal-user", "email_confirmed": True}
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "is_admin": False
    }

    with pytest.raises(HTTPException) as exc:
        await require_admin(user, mock_supabase)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_active_subscription_trial_active():
    user = {"id": "trial-user", "email_confirmed": True}
    mock_supabase = MagicMock()
    # Trial ending tomorrow (future)
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "TRIAL_ACTIVE",
        "trial_end_date": "2099-01-01T00:00:00Z"
    }

    res = await require_active_subscription(user, mock_supabase)
    assert res == user


@pytest.mark.asyncio
async def test_require_active_subscription_expired():
    user = {"id": "expired-user", "email_confirmed": True}
    mock_supabase = MagicMock()
    # Trial ended in past
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "subscription_status": "EXPIRED",
        "trial_end_date": "2020-01-01T00:00:00Z"
    }

    with pytest.raises(HTTPException) as exc:
        await require_active_subscription(user, mock_supabase)
    assert exc.value.status_code == 402


def test_auth_me_endpoint_unauthorized():
    client = TestClient(app)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_auth_me_endpoint_authorized():
    client = TestClient(app)
    
    mock_user = {"id": "test-user-id", "email": "test@test.com", "email_confirmed": True}
    mock_profile = {"id": "test-user-id", "email": "test@test.com", "display_name": "Test User", "is_admin": False}
    
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = mock_profile

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 200
        assert response.json()["display_name"] == "Test User"
    finally:
        app.dependency_overrides.clear()
