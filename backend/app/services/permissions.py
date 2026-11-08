from app.integrations.auth_service import CurrentUser

# Who may do what, from the team's permission matrix. Where the matrix says
# "Conditional" or "No by default", the choice made here is explained in the PR.
CREATE_JOBS = ("admin", "operator", "template_designer")
VIEW_RESULTS = ("admin", "operator", "template_designer", "viewer")
CORRECT_RESULTS = ("admin", "operator", "template_designer")
FINALIZE = ("admin", "operator")  # approving a result and finalizing a job
VIEW_AUDIT_LOG = ("admin",)


def owner_scope(user: CurrentUser) -> str | None:
    """None means 'may see everything' (admin). Anyone else sees only what they created."""
    return None if user.role == "admin" else user.user_id


def can_access(user: CurrentUser, created_by: str | None) -> bool:
    scope = owner_scope(user)
    return scope is None or created_by == scope