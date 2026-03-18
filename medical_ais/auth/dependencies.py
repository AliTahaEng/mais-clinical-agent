"""
FastAPI dependencies for authentication.
Import these into route files — never import token_utils directly in routes.
"""
from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from medical_ais.auth.models import User
from medical_ais.auth.token_utils import decode_token
from medical_ais.auth.user_store import UserStore
from medical_ais.config.settings import get_settings

_bearer = HTTPBearer(auto_error=False)


def _get_user_store(request: Request) -> UserStore:
    return request.app.state.container.user_store


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    user_store: UserStore = Depends(_get_user_store),
) -> User:
    """
    Validate Bearer JWT and return the current User.
    Raises 401 if token is missing, invalid, or expired.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise exc

    settings = get_settings()
    try:
        payload = decode_token(credentials.credentials, settings.jwt_secret)
        if payload.get("type") != "access":
            raise exc
        user_id: str = payload.get("sub", "")
    except JWTError:
        raise exc

    user = await user_store.get_by_id(user_id)
    if user is None or not user.is_active:
        raise exc
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    user_store: UserStore = Depends(_get_user_store),
) -> User | None:
    """Like get_current_user but returns None instead of raising on missing token."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, user_store)
    except HTTPException:
        return None


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require the current user to have the 'admin' role."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
