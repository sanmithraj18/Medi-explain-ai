"""
MediExplain AI — Security: JWT verification via Supabase Admin SDK.
Never import this module from any file accessible to the frontend.
"""
from fastapi import HTTPException, status
from supabase import Client


async def verify_supabase_token(token: str, supabase: Client) -> dict:
    """
    Verify a Supabase JWT by calling the Supabase Auth admin API.
    Returns the authenticated user dict, raises HTTPException on failure.

    We deliberately use the Supabase admin SDK (get_user) rather than
    manually decoding the JWT, so that Supabase-side revocations are
    respected without requiring the JWT secret in our env.
    """
    try:
        response = supabase.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {
            "id": response.user.id,
            "email": response.user.email,
            "email_confirmed": response.user.email_confirmed_at is not None,
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def extract_bearer_token(authorization: str | None) -> str:
    """Extract and return the raw token from 'Bearer <token>' header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token

