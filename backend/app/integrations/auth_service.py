import logging
from typing import Literal

from fastapi import Depends, Header
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import ApiError

logger = logging.getLogger(__name__)

Role = Literal["admin", "template_designer", "operator", "viewer"]
_VALID_ROLES = ("admin", "template_designer", "operator", "viewer")


class CurrentUser(BaseModel):
    user_id: str
    role: Role


_DEFAULT_USER = CurrentUser(user_id="user_001", role="operator")


def _unauthenticated() -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", "Authentication is required.")


def get_current_user(
    x_mock_user_id: str | None = Header(default=None),
    x_mock_role: str | None = Header(default=None),
) -> CurrentUser:
    """THE swap point for Member 5's authentication.

    This mock lets you act as different users by sending the headers X-Mock-User-Id and
    X-Mock-Role (the role 'anonymous' simulates a logged-out request). It is honoured only
    while ENVIRONMENT=development. Real authentication replaces this function.
    """
    if settings.environment != "development":
        raise _unauthenticated()
    if x_mock_user_id is None and x_mock_role is None:
        return _DEFAULT_USER
    role = x_mock_role or _DEFAULT_USER.role
    if role not in _VALID_ROLES:
        raise _unauthenticated()
    return CurrentUser(user_id=x_mock_user_id or _DEFAULT_USER.user_id, role=role)


def require_roles(*allowed: str):
    """THE swap point for Member 5's shared authorization utility."""

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            logger.warning(
                "Access denied: user %s (role %s) tried an action allowed for %s",
                user.user_id, user.role, allowed,
            )
            raise ApiError(403, "FORBIDDEN", "You do not have permission to perform this action.")
        return user

    return dependency