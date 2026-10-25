from typing import Literal

from pydantic import BaseModel


class CurrentUser(BaseModel):
    user_id: str
    role: Literal["admin", "operator", "viewer"]


def get_current_user() -> CurrentUser:
    """THE swap point for Member 5's login. For now everyone is the same fake operator."""
    return CurrentUser(user_id="user_001", role="operator")