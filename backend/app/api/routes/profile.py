import os
import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.api.dependencies import get_current_admin

router = APIRouter()

# Fixed local paths for single-user profile persistence
DATA_DIR = Path("data")
PROFILE_JSON_PATH = DATA_DIR / "profile.json"
AVATAR_DIR = DATA_DIR / "profile"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

class ProfileUpdate(BaseModel):
    display_name: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

def _ensure_dirs():
    os.makedirs(AVATAR_DIR, exist_ok=True)

def _get_profile_data() -> dict:
    _ensure_dirs()
    if PROFILE_JSON_PATH.exists():
        try:
            with open(PROFILE_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "display_name": "Admin User",
        "username": "admin",
        "role_label": "Administrator",
        "avatar_filename": None
    }

def _save_profile_data(data: dict):
    _ensure_dirs()
    with open(PROFILE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def _update_env_password_hash(new_hash: str):
    from app.config import _ENV_PATH, settings
    import re
    import datetime
    
    if not _ENV_PATH.exists():
        raise Exception(".env file not found")
        
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Replace the hash using regex
    new_content = re.sub(
        r'^NEOALGO_ADMIN_PASSWORD_HASH=.*$',
        f'NEOALGO_ADMIN_PASSWORD_HASH="{new_hash}"',
        content,
        flags=re.MULTILINE
    )
    
    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    # Update settings immediately
    settings.neoalgo_admin_password_hash = new_hash

@router.get("")
def get_profile():
    data = _get_profile_data()
    # Always set username to admin for security and single-user constraint
    data["username"] = "admin"
    data["role_label"] = "Administrator"
    
    avatar_url = "/api/profile/avatar" if data.get("avatar_filename") else None
    
    return {
        "display_name": data.get("display_name", "Admin User"),
        "username": data["username"],
        "role_label": data["role_label"],
        "avatar_url": avatar_url,
        "avatar_filename": data.get("avatar_filename")
    }

@router.put("")
def update_profile(update: ProfileUpdate):
    if not update.display_name or len(update.display_name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Display name cannot be empty")
        
    data = _get_profile_data()
    data["display_name"] = update.display_name.strip()
    _save_profile_data(data)
    
    return get_profile()

@router.put("/password")
def change_password(request: PasswordChangeRequest, username: str = Depends(get_current_admin)):
    from app.config import settings
    from app.services.auth_service import verify_password, ph
    from app.api.routes.auth import LOGIN_ATTEMPTS, MAX_ATTEMPTS, LOCKOUT_WINDOW
    import time
    
    # Rate limiting specifically for password change
    now = time.time()
    rate_limit_key = f"{username}_pwd_change"
    LOGIN_ATTEMPTS[rate_limit_key] = [t for t in LOGIN_ATTEMPTS[rate_limit_key] if now - t < LOCKOUT_WINDOW]
    
    if len(LOGIN_ATTEMPTS[rate_limit_key]) >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later."
        )
    
    if len(request.new_password) < 12:
        raise HTTPException(status_code=422, detail="New password must be at least 12 characters.")
        
    if request.new_password == request.current_password:
        raise HTTPException(status_code=422, detail="New password cannot be identical to the current password.")
        
    valid_hash = settings.neoalgo_admin_password_hash
    
    if not valid_hash or not verify_password(request.current_password, valid_hash):
        LOGIN_ATTEMPTS[rate_limit_key].append(now)
        import asyncio
        # Blocking sleep instead of asyncio.sleep because it's a synchronous endpoint
        time.sleep(0.5) 
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect."
        )
        
    LOGIN_ATTEMPTS.pop(rate_limit_key, None)
    
    try:
        new_hash = ph.hash(request.new_password)
        _update_env_password_hash(new_hash)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to persist new password")
        
    return {"message": "Password changed successfully"}

@router.post("/avatar")
async def upload_avatar(file: UploadFile = File(...)):
    _ensure_dirs()
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
        
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: JPG, PNG, WEBP.")
    
    # Read file to check size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")
        
    # Safe filename (no traversal)
    safe_filename = f"avatar{ext}"
    safe_path = AVATAR_DIR / safe_filename
    
    # Write file
    with open(safe_path, "wb") as f:
        f.write(contents)
        
    # Update profile state
    data = _get_profile_data()
    data["avatar_filename"] = safe_filename
    _save_profile_data(data)
    
    return get_profile()

@router.delete("/avatar")
def delete_avatar():
    data = _get_profile_data()
    if data.get("avatar_filename"):
        avatar_path = AVATAR_DIR / data["avatar_filename"]
        if avatar_path.exists():
            os.remove(avatar_path)
        data["avatar_filename"] = None
        _save_profile_data(data)
    
    return get_profile()

@router.get("/avatar")
def get_avatar():
    data = _get_profile_data()
    if not data.get("avatar_filename"):
        raise HTTPException(status_code=404, detail="Avatar not found")
        
    avatar_path = AVATAR_DIR / data["avatar_filename"]
    
    # Safety check
    if not avatar_path.resolve().is_relative_to(AVATAR_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Path traversal prevented")
        
    if not avatar_path.exists():
        raise HTTPException(status_code=404, detail="Avatar file missing")
        
    return FileResponse(avatar_path)
