import pytest
from httpx import AsyncClient
from app.main import app
from app.config import settings
import os
from pathlib import Path

TEST_DATA_DIR = Path("data")
PROFILE_JSON_PATH = TEST_DATA_DIR / "profile.json"
AVATAR_DIR = TEST_DATA_DIR / "profile"

def _cleanup_test_data():
    if PROFILE_JSON_PATH.exists():
        os.remove(PROFILE_JSON_PATH)
    if AVATAR_DIR.exists():
        for f in AVATAR_DIR.iterdir():
            if f.is_file():
                os.remove(f)

@pytest.fixture(autouse=True)
def run_around_tests():
    _cleanup_test_data()
    yield
    _cleanup_test_data()

async def get_auth_cookies(ac: AsyncClient):
    # Ensure there is a test admin password hash so login can succeed.
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    settings.neoalgo_admin_password_hash = ph.hash("testpassword")
    
    response = await ac.post("/api/auth/login", json={"username": "admin", "password": "testpassword"})
    return response.cookies

@pytest.mark.asyncio
async def test_get_profile_unauthenticated():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/api/profile")
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_get_profile_authenticated():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        cookies = await get_auth_cookies(ac)
        response = await ac.get("/api/profile", cookies=cookies)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "admin"
        assert data["role_label"] == "Administrator"
        assert "password" not in data
        assert "jwt" not in data

@pytest.mark.asyncio
async def test_update_profile():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        cookies = await get_auth_cookies(ac)
        
        # Valid update
        response = await ac.put("/api/profile", json={"display_name": "New Admin Name"}, cookies=cookies)
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "New Admin Name"
        
        # Invalid update
        response = await ac.put("/api/profile", json={"display_name": "   "}, cookies=cookies)
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_upload_avatar_unauthenticated():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/profile/avatar", files={"file": ("test.jpg", b"fake image content", "image/jpeg")})
        assert response.status_code == 401

@pytest.mark.asyncio
async def test_upload_avatar_authenticated_valid():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        cookies = await get_auth_cookies(ac)
        response = await ac.post("/api/profile/avatar", files={"file": ("test.png", b"fake png content", "image/png")}, cookies=cookies)
        assert response.status_code == 200
        data = response.json()
        assert data["avatar_url"] == "/api/profile/avatar"
        assert data["avatar_filename"] == "avatar.png"

@pytest.mark.asyncio
async def test_upload_avatar_invalid_type():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        cookies = await get_auth_cookies(ac)
        response = await ac.post("/api/profile/avatar", files={"file": ("test.txt", b"fake text content", "text/plain")}, cookies=cookies)
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

@pytest.mark.asyncio
async def test_upload_avatar_too_large():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        cookies = await get_auth_cookies(ac)
        large_content = b"0" * (5 * 1024 * 1024 + 1)
        response = await ac.post("/api/profile/avatar", files={"file": ("test.jpg", large_content, "image/jpeg")}, cookies=cookies)
        assert response.status_code == 400
        assert "too large" in response.json()["detail"]

@pytest.mark.asyncio
async def test_delete_avatar():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        cookies = await get_auth_cookies(ac)
        
        # Upload first
        await ac.post("/api/profile/avatar", files={"file": ("test.png", b"fake png content", "image/png")}, cookies=cookies)
        
        # Delete
        response = await ac.delete("/api/profile/avatar", cookies=cookies)
        assert response.status_code == 200
        data = response.json()
        assert data["avatar_url"] is None
        assert data["avatar_filename"] is None

@pytest.mark.asyncio
async def test_get_avatar():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        cookies = await get_auth_cookies(ac)
        
        # Upload
        await ac.post("/api/profile/avatar", files={"file": ("test.png", b"fake png content", "image/png")}, cookies=cookies)
        
        # Fetch
        response = await ac.get("/api/profile/avatar", cookies=cookies)
        assert response.status_code == 200
        assert response.content == b"fake png content"
        
@pytest.mark.asyncio
async def test_path_traversal_prevention():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        cookies = await get_auth_cookies(ac)
        from app.api.routes.profile import _save_profile_data, _get_profile_data
        
        data = _get_profile_data()
        data["avatar_filename"] = "../../../etc/passwd"
        _save_profile_data(data)
        
        response = await ac.get("/api/profile/avatar", cookies=cookies)
        assert response.status_code in [403, 404]
