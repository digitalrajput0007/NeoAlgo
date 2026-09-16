import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

@pytest.fixture
def auth_headers():
    response = client.post("/api/auth/login", json={"username": "admin", "password": "old_password_admin"})
    if response.status_code == 200:
        return {"Cookie": response.headers.get("set-cookie")}
    return {}

@pytest.fixture
def setup_password():
    from app.services.auth_service import ph
    import re
    # Store old hash
    original_hash = settings.neoalgo_admin_password_hash
    # Set to a known password
    settings.neoalgo_admin_password_hash = ph.hash("old_password_admin")
    
    yield
    
    # Restore old hash
    settings.neoalgo_admin_password_hash = original_hash

from unittest.mock import patch

def test_password_change_success(setup_password, auth_headers):
    with patch("app.api.routes.profile._update_env_password_hash") as mock_update:
        response = client.put(
            "/api/profile/password",
            json={"current_password": "old_password_admin", "new_password": "new_secure_password_123"},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Password changed successfully"
        mock_update.assert_called_once()
        
        # Test 8: Password hash is changed (verified by mock being called with new hash)
        new_hash_arg = mock_update.call_args[0][0]
        assert new_hash_arg != settings.neoalgo_admin_password_hash
        assert "$argon2id$" in new_hash_arg

def test_password_change_incorrect_current(setup_password, auth_headers):
    response = client.put(
        "/api/profile/password",
        json={"current_password": "wrong_password", "new_password": "new_secure_password_123"},
        headers=auth_headers
    )
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()

def test_password_change_missing_fields(setup_password, auth_headers):
    response = client.put(
        "/api/profile/password",
        json={"current_password": "old_password_admin"},
        headers=auth_headers
    )
    assert response.status_code == 422 # missing new_password

def test_password_change_too_short(setup_password, auth_headers):
    response = client.put(
        "/api/profile/password",
        json={"current_password": "old_password_admin", "new_password": "short"},
        headers=auth_headers
    )
    assert response.status_code == 422
    assert "12 characters" in response.json()["detail"]

def test_password_change_identical(setup_password, auth_headers):
    response = client.put(
        "/api/profile/password",
        json={"current_password": "old_password_admin", "new_password": "old_password_admin"},
        headers=auth_headers
    )
    assert response.status_code == 422
    assert "identical" in response.json()["detail"]

def test_password_change_unauthenticated():
    response = client.put(
        "/api/profile/password",
        json={"current_password": "old_password_admin", "new_password": "new_secure_password_123"}
    )
    assert response.status_code == 401

def test_session_invalidated_after_change(setup_password, auth_headers):
    with patch("app.api.routes.profile._update_env_password_hash") as mock_update:
        # Mock settings change
        def side_effect(new_hash):
            settings.neoalgo_admin_password_hash = new_hash
            
        mock_update.side_effect = side_effect
        
        # 1. Change password successfully
        response = client.put(
            "/api/profile/password",
            json={"current_password": "old_password_admin", "new_password": "new_secure_password_123"},
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # 2. Try to use old session token on a protected endpoint
        status_resp = client.get("/api/auth/status", headers=auth_headers)
        assert status_resp.status_code == 401
        assert "Session expired" in status_resp.json()["detail"]
