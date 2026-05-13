"""Compatibility wrapper: JWT config lives in ``backend.auth``."""
from backend.auth import access_token_ttl_minutes as access_token_expire_minutes
from backend.auth import algorithm as jwt_algorithm
from backend.auth import jwt_secret

__all__ = ["jwt_secret", "jwt_algorithm", "access_token_expire_minutes"]
