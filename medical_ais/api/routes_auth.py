"""
Authentication routes: register, login, logout, refresh, me.
"""
from __future__ import annotations

import hashlib

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from medical_ais.auth.dependencies import get_current_user
from medical_ais.auth.models import User
from medical_ais.auth.token_utils import (
    create_access_token,
    create_refresh_token,
    verify_password,
)
from medical_ais.auth.user_store import UserStore
from medical_ais.config.settings import get_settings
from medical_ais.api.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

logger = structlog.get_logger(__name__)
auth_router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"


def _get_user_store(request: Request) -> UserStore:
    return request.app.state.container.user_store


def _token_hash(token: str) -> str:
    """SHA-256 hash of the raw refresh token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def _set_refresh_cookie(response: Response, token: str, days: int) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=False,       # set True in production with HTTPS
        samesite="lax",
        max_age=days * 86400,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=_REFRESH_COOKIE, path="/api/v1/auth")
    response.delete_cookie(key="auth-session", path="/")


async def _build_token_response(
    user: User,
    response: Response,
    user_store: UserStore,
) -> TokenResponse:
    """Create access + refresh tokens, persist refresh hash, set cookie, return response."""
    settings = get_settings()

    access_token = create_access_token(
        {"sub": user.id, "role": user.role, "username": user.username},
        secret=settings.jwt_secret,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )
    refresh_token = create_refresh_token(
        {"sub": user.id},
        secret=settings.jwt_secret,
        expires_days=settings.jwt_refresh_token_expire_days,
    )

    await user_store.save_refresh_token(
        user.id,
        _token_hash(refresh_token),
        expires_days=settings.jwt_refresh_token_expire_days,
    )
    _set_refresh_cookie(response, refresh_token, settings.jwt_refresh_token_expire_days)

    # Non-httpOnly session hint cookie — readable by Next.js middleware for routing decisions.
    # Contains ONLY role + loggedIn flag, NOT the actual JWT.
    # URL-encoded so Python's http.cookies doesn't mangle commas/quotes with octal escapes.
    import json as _json
    import urllib.parse as _urlparse
    raw_session = _json.dumps({"loggedIn": True, "role": user.role})
    response.set_cookie(
        key="auth-session",
        value=_urlparse.quote(raw_session, safe=""),
        httponly=False,
        secure=False,
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/",
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            role=user.role,
        ),
    )


# ── Register ──────────────────────────────────────────────────────────────────

@auth_router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    response: Response,
    user_store: UserStore = Depends(_get_user_store),
) -> TokenResponse:
    existing = await user_store.get_by_email(body.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        user = await user_store.create_user(
            email=body.email,
            username=body.username,
            plain_password=body.password,
            role="user",
        )
    except Exception as exc:
        logger.warning("register.failed", error=str(exc))
        raise HTTPException(status_code=400, detail="Username or email already taken")

    logger.info("auth.registered", user_id=user.id)
    return await _build_token_response(user, response, user_store)


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    user_store: UserStore = Depends(_get_user_store),
) -> TokenResponse:
    user = await user_store.get_by_email(body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    logger.info("auth.login", user_id=user.id, role=user.role)
    return await _build_token_response(user, response, user_store)


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_router.post("/logout", status_code=204)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
    user_store: UserStore = Depends(_get_user_store),
    current_user: User = Depends(get_current_user),
) -> None:
    if refresh_token:
        await user_store.validate_and_revoke_refresh_token(_token_hash(refresh_token))
    _clear_refresh_cookie(response)
    logger.info("auth.logout", user_id=current_user.id)


# ── Refresh ───────────────────────────────────────────────────────────────────

@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
    user_store: UserStore = Depends(_get_user_store),
) -> TokenResponse:
    _session_expired = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expired — please log in again",
    )

    if not refresh_token:
        raise _session_expired

    user_id = await user_store.validate_and_revoke_refresh_token(_token_hash(refresh_token))
    if not user_id:
        _clear_refresh_cookie(response)
        raise _session_expired

    user = await user_store.get_by_id(user_id)
    if not user or not user.is_active:
        _clear_refresh_cookie(response)
        raise _session_expired

    return await _build_token_response(user, response, user_store)


# ── Me ────────────────────────────────────────────────────────────────────────

@auth_router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        role=current_user.role,
    )
