"""Supabase JWT verification and FastAPI auth dependencies."""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.tenant import Tenant
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def _supabase_issuer() -> str:
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


def _supabase_jwks_url() -> str:
    return f"{_supabase_issuer()}/.well-known/jwks.json"


def _decode_with_hs_secret(token: str, algorithm: str) -> dict:
    secret = (settings.supabase_jwt_secret or "").strip()
    if not secret or secret == "your-jwt-secret":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Supabase token uses HMAC signing, but SUPABASE_JWT_SECRET is missing. "
                "Set the project JWT secret in backend .env."
            ),
        )
    return jwt.decode(
        token,
        secret,
        algorithms=[algorithm],
        issuer=_supabase_issuer(),
        options={"verify_aud": False},
    )


def _decode_with_jwks(token: str, algorithm: str) -> dict:
    jwks_client = jwt.PyJWKClient(_supabase_jwks_url())
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=[algorithm],
        issuer=_supabase_issuer(),
        options={"verify_aud": False},
    )


def decode_supabase_token(token: str) -> dict:
    """Verify and decode Supabase JWT for both HMAC and asymmetric signing."""
    try:
        header = jwt.get_unverified_header(token)
        algorithm = str(header.get("alg", "")).upper()
        if not algorithm:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header: missing alg")

        if algorithm.startswith("HS"):
            payload = _decode_with_hs_secret(token, algorithm)
        else:
            payload = _decode_with_jwks(token, algorithm)

        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.InvalidSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature — verify Supabase project keys/JWKS configuration",
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer")
    except jwt.PyJWKClientError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Could not validate token key: {exc}")
    except jwt.DecodeError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token decode error: {exc}")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {exc}")


def _normalize_token(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    cleaned = token.strip()
    if cleaned.lower().startswith("bearer "):
        cleaned = cleaned.split(" ", 1)[1].strip()
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return cleaned


async def _upsert_user_from_payload(payload: dict, db: AsyncSession) -> User:
    supabase_uid = payload.get("sub")
    email = payload.get("email")
    if not supabase_uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.supabase_user_id == supabase_uid))
    user = result.scalar_one_or_none()

    if user:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
        return user

    # Existing legacy/local user with same email: link account to Supabase user id.
    if email:
        email_result = await db.execute(select(User).where(User.email == email))
        email_user = email_result.scalar_one_or_none()
        if email_user:
            if not email_user.is_active:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is inactive")
            if email_user.supabase_user_id != supabase_uid:
                email_user.supabase_user_id = supabase_uid
                try:
                    await db.commit()
                except IntegrityError:
                    await db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Email is already linked to another account",
                    )
                await db.refresh(email_user)
            return email_user

    # Auto-provision on first authenticated request
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.is_active.is_(True)).order_by(Tenant.created_at).limit(1)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active tenant available",
        )

    user = User(
        supabase_user_id=supabase_uid,
        tenant_id=tenant.id,
        email=email or "",
        role="admin",
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not provision user account due to unique constraint",
        )
    await db.refresh(user)
    return user


async def get_user_from_token(token: str, db: AsyncSession) -> User:
    payload = decode_supabase_token(_normalize_token(token))
    return await _upsert_user_from_payload(payload, db)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials if credentials else None
    return await get_user_from_token(token or "", db)


async def get_current_tenant_id(user: User = Depends(get_current_user)) -> str:
    return user.tenant_id


async def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return user
