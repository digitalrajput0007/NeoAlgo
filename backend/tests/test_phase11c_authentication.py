import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_authentication_flow():
    async with AsyncClient(app=app, base_url="https://test") as ac:
        # 1. Unauthenticated request to a protected endpoint
        response = await ac.get("/api/dashboard/summary")
        assert response.status_code == 401

        # 2. Failed login
        response = await ac.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
        assert response.status_code == 401

        # 3. Successful login
        response = await ac.post("/api/auth/login", json={"username": "admin", "password": "admin"})
        assert response.status_code == 200
        assert "session_token" in response.cookies

        # 4. Check auth status
        response = await ac.get("/api/auth/status")
        assert response.status_code == 200
        assert response.json()["authenticated"] is True

        # 5. Authenticated request to protected endpoint
        response = await ac.get("/api/dashboard/summary")
        assert response.status_code == 200

        # 6. Logout
        response = await ac.post("/api/auth/logout")
        assert response.status_code == 200
        assert "session_token" not in response.cookies or not response.cookies.get("session_token")

        # 7. Check unauthenticated after logout
        response = await ac.get("/api/dashboard/summary")
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_rate_limiting():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        for _ in range(5):
            response = await ac.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
            assert response.status_code in [401, 429]
        
        # 6th attempt should be rate limited (429)
        response = await ac.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert response.status_code == 429
