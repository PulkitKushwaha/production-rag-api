"""
Authentication Middleware
 
Supports two auth methods:
 
1. API Key (X-API-Key header)
   Simple, stateless, suitable for server-to-server calls.
   Keys are stored in environment variables (or secrets manager).
   No expiry, just rotate by updating the key list.
2. JWT Bearer Token (Authorization: Bearer <token>)
   Suitable for user-facing applications.
   Tokens expire after configurable duration.
   Useful when different users need different permissions.
Design decision: both methods check against the same routes.
Routes declare which auth method they require via dependency.
Routes with no auth dependency are public (health, root).
"""
 
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import secrets
 
from app.core.config import settings
 
 
# ── Security scheme definitions ───────────────────────────────
 
bearer_scheme = HTTPBearer(auto_error=False)
api_key_scheme = APIKeyHeader(
    name=settings.api_key_header,
    auto_error=False
)
 
 
# ── API Key authentication ────────────────────────────────────
 
async def verify_api_key(
    api_key: Optional[str] = Security(api_key_scheme)
) -> str:
    """
    Verify API key from X-API-Key header.
 
    Returns the API key if valid.
    Raises 401 if missing or invalid.
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Add X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )
 
    # Constant-time comparison to prevent timing attacks
    valid_keys = settings.api_keys_list
    for valid_key in valid_keys:
        if secrets.compare_digest(api_key, valid_key):
            return api_key
 
    raise HTTPException(
        status_code=401,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "ApiKey"}
    )
 
 
# ── JWT authentication ────────────────────────────────────────
 
def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.
 
    Args:
        data          : Payload to encode in the token
        expires_delta : Token lifetime (default: settings.jwt_expire_minutes)
 
    Returns:
        Encoded JWT string
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    )
    to_encode.update({"exp": expire})
 
    return jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm
    )
 
 
async def verify_jwt_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> dict:
    """
    Verify JWT Bearer token from Authorization header.
 
    Returns the decoded token payload if valid.
    Raises 401 if missing, expired, or invalid.
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Bearer token required. Add Authorization: Bearer <token> header.",
            headers={"WWW-Authenticate": "Bearer"}
        )
 
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
 
    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )
 
 
# ── Flexible auth — accepts either method ─────────────────────
 
async def verify_any_auth(
    api_key: Optional[str] = Security(api_key_scheme),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> str:
    """
    Accept either API key or JWT token.
 
    Returns a string identifier for the authenticated caller.
    Used on endpoints that support both auth methods.
    """
    # Try API key first (faster — no JWT decode needed)
    if api_key:
        valid_keys = settings.api_keys_list
        for valid_key in valid_keys:
            if secrets.compare_digest(api_key, valid_key):
                return f"api_key:{api_key[:8]}..."
 
    # Try JWT
    if credentials:
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.secret_key,
                algorithms=[settings.jwt_algorithm]
            )
            return f"jwt:{payload.get('sub', 'unknown')}"
        except JWTError:
            pass
 
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide X-API-Key header or Authorization: Bearer token.",
        headers={"WWW-Authenticate": "ApiKey, Bearer"}
    )