import asyncio
from fastapi import APIRouter, Response, HTTPException, status, Depends
from pydantic import BaseModel
from app.config import settings
from app.services.auth_service import verify_password, create_access_token
from app.api.dependencies import get_current_admin
import logging
from collections import defaultdict
import time

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

class LoginRequest(BaseModel):
    username: str
    password: str

# Simple in-memory rate limiting for login
LOGIN_ATTEMPTS = defaultdict(list)
MAX_ATTEMPTS = 5
LOCKOUT_WINDOW = 300  # 5 minutes

@router.post("/login")
async def login(request: LoginRequest, response: Response):
    now = time.time()
    
    # Cleanup old attempts
    LOGIN_ATTEMPTS[request.username] = [t for t in LOGIN_ATTEMPTS[request.username] if now - t < LOCKOUT_WINDOW]
    
    if len(LOGIN_ATTEMPTS[request.username]) >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later."
        )

    # Adding a small deliberate delay to mitigate timing attacks
    await asyncio.sleep(0.5)

    valid_username = settings.neoalgo_admin_username
    valid_hash = settings.neoalgo_admin_password_hash

    is_username_correct = (request.username == valid_username)
    is_password_correct = False

    if is_username_correct and valid_hash:
        is_password_correct = verify_password(request.password, valid_hash)
        
    if not is_username_correct or not is_password_correct:
        LOGIN_ATTEMPTS[request.username].append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
        
    # Clear attempts on success
    LOGIN_ATTEMPTS.pop(request.username, None)
    
    # Generate token
    token = create_access_token(data={"sub": request.username})
    
    is_production = settings.neoalgo_env.lower() == "production"
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=settings.neoalgo_session_timeout_hours * 3600
    )
    
    return {"status": "ok", "message": "Logged in successfully"}

@router.post("/logout")
async def logout(response: Response):
    is_production = settings.neoalgo_env.lower() == "production"
    response.delete_cookie(
        key="session_token",
        httponly=True,
        secure=is_production,
        samesite="lax"
    )
    return {"status": "ok", "message": "Logged out successfully"}

@router.get("/status")
async def check_auth_status(username: str = Depends(get_current_admin)):
    return {"authenticated": True, "username": username}
