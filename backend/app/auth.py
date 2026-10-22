"""Neon Auth JWT verification. Server decides identity; client claims are never trusted."""
from urllib.parse import urlparse

import jwt
from fastapi import Header, HTTPException
from jwt import PyJWKClient

from .config import settings

_u = urlparse(settings.NEON_AUTH_BASE_URL)
ISSUER = f"{_u.scheme}://{_u.netloc}"
_jwks = PyJWKClient(settings.NEON_AUTH_JWKS_URL, cache_keys=True, lifespan=3600)


def current_user_id(authorization: str | None = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "unauthorized")
    token = authorization[7:]
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key,
            algorithms=["EdDSA", "RS256", "ES256"],
            issuer=ISSUER, audience=ISSUER,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, "auth_unavailable")
    except Exception:
        raise HTTPException(401, "unauthorized")
    return str(claims["sub"])
