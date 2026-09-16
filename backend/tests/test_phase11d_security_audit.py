import pytest
from httpx import AsyncClient
from app.main import app
from app.config import settings

@pytest.mark.asyncio
async def test_public_endpoints_unauthenticated():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        # Verify no secrets in health endpoint
        assert "telegram_session" not in data
        assert "database_url" not in data
        assert "secret" not in data
        
        response = await ac.get("/")
        assert response.status_code == 200

@pytest.mark.asyncio
async def test_protected_api_without_auth():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # GET endpoints
        for endpoint in [
            "/api/dashboard/summary",
            "/api/telegram/status",
            "/api/broker/status"
        ]:
            response = await ac.get(endpoint)
            assert response.status_code == 401

        # POST endpoints
        for endpoint in [
            "/api/trading/pause",
            "/api/trading/resume",
            "/api/trading/emergency-close",
            "/api/telegram/disconnect",
        ]:
            response = await ac.post(endpoint)
            assert response.status_code == 401

@pytest.mark.asyncio
async def test_security_headers_and_cors():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.options(
            "/api/health", 
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

        response = await ac.get("/api/health")
        # Security headers check
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

@pytest.mark.asyncio
async def test_login_and_logout_flow():
    async with AsyncClient(app=app, base_url="https://test") as ac:
        # Invalid login fails
        response = await ac.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
        assert response.status_code == 401

        # Valid login succeeds
        response = await ac.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200
        assert "session_token" in response.cookies
        
        # Verify HttpOnly and SameSite
        cookie = response.headers.get("set-cookie")
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie.lower() or "samesite=lax" in cookie.lower()
        
        if settings.neoalgo_env.lower() == "production":
            assert "Secure" in cookie

        # Use token to access protected route
        response = await ac.get("/api/dashboard/summary")
        assert response.status_code == 200
        # Check no secrets in API response
        assert "secret" not in str(response.content).lower()

        # Logout invalidates session
        response = await ac.post("/api/auth/logout")
        assert response.status_code == 200
        
        # Access denied after logout
        response = await ac.get("/api/dashboard/summary")
        assert response.status_code == 401
