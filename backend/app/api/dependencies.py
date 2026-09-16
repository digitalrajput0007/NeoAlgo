from fastapi import Request, HTTPException, status
from app.services.auth_service import decode_access_token

async def get_current_admin(request: Request):
    """
    Dependency to verify the presence and validity of the session_token cookie.
    Raises 401 Unauthorized if missing or invalid.
    """
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )
    
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session format",
        )
        
    from app.config import settings
    current_pwd_rev = settings.neoalgo_admin_password_hash[-8:] if settings.neoalgo_admin_password_hash else "default"
    token_pwd_rev = payload.get("pwd_rev")
    
    if token_pwd_rev and token_pwd_rev != current_pwd_rev:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired due to password change",
        )
        
    return username
