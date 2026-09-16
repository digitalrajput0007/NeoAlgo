from fastapi import APIRouter, Depends, HTTPException, Body
from app.brokers.kotak_neo import get_kotak_broker
from typing import Dict, Any, Optional

router = APIRouter()

kotak_broker = get_kotak_broker()

@router.get("/kotak/status")
async def get_kotak_status() -> Dict[str, Any]:
    """Returns the authentication and connection status of Kotak Neo"""
    if kotak_broker.auth_status == "DISCONNECTED":
        await kotak_broker.authenticate()
            
    profile = None
    if kotak_broker.auth_status == "CONNECTED":
        profile = await kotak_broker.get_profile()
        
    return {
        "auth_status": kotak_broker.auth_status, # CONNECTED, DISCONNECTED, AUTHENTICATION_BLOCKED
        "read_only": True,
        "last_successful_request": kotak_broker.last_successful_request,
        "profile": profile
    }

@router.post("/kotak/authenticate")
async def authenticate_kotak(payload: Optional[Dict[str, str]] = Body(default=None)) -> Dict[str, Any]:
    """Allows triggering authentication with optional fresh TOTP code or TOTP secret."""
    totp_code = payload.get("totp") if payload else None
    totp_secret = payload.get("totp_secret") if payload else None
    
    success = await kotak_broker.authenticate(totp_code=totp_code, totp_secret=totp_secret)
    return {
        "success": success,
        "auth_status": kotak_broker.auth_status,
        "read_only": True,
    }

@router.get("/kotak/positions")
async def get_kotak_positions() -> Dict[str, Any]:
    if not kotak_broker.is_connected:
        await kotak_broker.authenticate()
    positions = await kotak_broker.get_positions()
    return {"positions": positions}

@router.get("/kotak/orders")
async def get_kotak_orders() -> Dict[str, Any]:
    if not kotak_broker.is_connected:
        await kotak_broker.authenticate()
    orders = await kotak_broker.get_orders()
    return {"orders": orders}
