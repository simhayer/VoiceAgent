"""Authentication endpoints for Supabase-based auth."""

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import get_current_user
from app.config import settings
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class UserProfile(BaseModel):
    id: str
    email: str
    tenant_id: str
    role: str

    model_config = {"from_attributes": True}


@router.get("/me", response_model=UserProfile)
async def get_me(user: User = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return user


class DebugTokenRequest(BaseModel):
    access_token: str


@router.post("/debug-token")
async def debug_token(body: DebugTokenRequest):
    """Decode a token WITHOUT verification and report diagnostics.
    Remove this endpoint before going to production.
    """
    if not settings.enable_auth_debug_endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    token = body.access_token

    # 1. Decode header (no verification)
    try:
        header = pyjwt.get_unverified_header(token)
    except Exception as exc:
        return {"error": f"Cannot read token header: {exc}"}

    # 2. Decode payload without any verification
    try:
        unverified_payload = pyjwt.decode(
            token,
            options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
            algorithms=["HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256"],
        )
    except Exception as exc:
        unverified_payload = {"decode_error": str(exc)}

    # 3. Try verified decode
    verify_error = None
    try:
        pyjwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256", "HS384", "HS512"],
            options={"verify_aud": False},
        )
    except Exception as exc:
        verify_error = f"{type(exc).__name__}: {exc}"

    return {
        "header": header,
        "payload_keys": list(unverified_payload.keys()),
        "sub": unverified_payload.get("sub"),
        "email": unverified_payload.get("email"),
        "aud": unverified_payload.get("aud"),
        "exp": unverified_payload.get("exp"),
        "jwt_secret_first_8": settings.supabase_jwt_secret[:8] + "..." if settings.supabase_jwt_secret else "(empty)",
        "verify_result": "OK" if not verify_error else verify_error,
    }
