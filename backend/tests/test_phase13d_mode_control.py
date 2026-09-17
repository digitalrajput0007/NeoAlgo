import pytest
from httpx import AsyncClient
import os
from pathlib import Path

from app.main import app
from app.config import settings
from app.api.dependencies import get_current_admin

async def override_get_current_admin():
    return {"id": 1, "username": "admin"}

@pytest.fixture(autouse=True)
def reset_settings():
    # Store original settings
    orig_mode = settings.neoalgo_mode
    orig_live = settings.live_trading_enabled
    
    settings.neoalgo_mode = "PAPER"
    settings.live_trading_enabled = False
    
    yield
    
    settings.neoalgo_mode = orig_mode
    settings.live_trading_enabled = orig_live

@pytest.mark.asyncio
async def test_mode_control_unauthenticated():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.get("/api/trading/mode")
        assert res.status_code == 401
        
        res = await ac.post("/api/trading/mode", json={
            "mode": "LIVE",
            "live_trading_enabled": True,
            "confirmation": True
        })
        assert res.status_code == 401

@pytest.mark.asyncio
async def test_mode_control_default_is_paper():
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.get("/api/trading/mode")
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "PAPER"
        assert data["live_trading_enabled"] is False
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_live_mode_rejected_without_confirmation():
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.post("/api/trading/mode", json={
            "mode": "LIVE",
            "live_trading_enabled": True,
            "confirmation": False
        })
        assert res.status_code == 400
        assert "Explicit confirmation required" in res.text
        
        # Verify mode didn't change
        assert settings.neoalgo_mode == "PAPER"
        assert settings.live_trading_enabled is False
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_live_mode_rejected_without_live_trading_enabled():
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.post("/api/trading/mode", json={
            "mode": "LIVE",
            "live_trading_enabled": False,
            "confirmation": True
        })
        assert res.status_code == 400
        assert "LIVE mode requires live_trading_enabled to be true" in res.text
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_live_mode_accepted_with_confirmation():
    app.dependency_overrides[get_current_admin] = override_get_current_admin
    async with AsyncClient(app=app, base_url="http://test") as ac:
        res = await ac.post("/api/trading/mode", json={
            "mode": "LIVE",
            "live_trading_enabled": True,
            "confirmation": True
        })
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "LIVE"
        assert data["live_trading_enabled"] is True
        
        # In-memory settings should be updated
        assert settings.neoalgo_mode == "LIVE"
        assert settings.live_trading_enabled is True
        
        # Verify it switches back to PAPER
        res = await ac.post("/api/trading/mode", json={
            "mode": "PAPER",
            "live_trading_enabled": False,
            "confirmation": True
        })
        assert res.status_code == 200
        assert settings.neoalgo_mode == "PAPER"
        assert settings.live_trading_enabled is False
    app.dependency_overrides.clear()
