from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_current_user

from app.models.user import User
from app.models.workspace_member import WorkspaceMember

from app.schemas.user import UserRead


router = APIRouter(
    prefix="/api/users",
    tags=["Users"],
)


# --------------------------------------------------
# DIRECT USER CREATION DISABLED
# --------------------------------------------------

@router.post(
    "",
    status_code=status.HTTP_410_GONE,
)
def create_user():
    """
    Direct passwordless user creation has been disabled.

    New users must register through /api/auth/register.
    Existing workspace owners/admins can invite users
    through the workspace invitation system.
    """

    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Direct user creation is disabled. "
            "New users must register through /api/auth/register. "
            "To add someone to a workspace, create an invitation "
            "through /api/workspaces/{workspace_id}/invitations."
        ),
    )


# --------------------------------------------------
# LIST USERS IN THE CURRENT USER'S WORKSPACES
# --------------------------------------------------

@router.get(
    "",
    response_model=list[UserRead],
)
def get_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return active users who share at least one active workspace
    with the authenticated user.

    Users from unrelated workspaces are never exposed.
    """

    # Find the workspaces where the current user is active.
    current_user_workspace_ids = (
        db.query(WorkspaceMember.workspace_id)
        .filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.membership_status == "active",
        )
        .subquery()
    )

    # Return active users who belong to one of those workspaces.
    workspace_users = (
        db.query(User)
        .join(
            WorkspaceMember,
            WorkspaceMember.user_id == User.id,
        )
        .filter(
            WorkspaceMember.workspace_id.in_(
                current_user_workspace_ids
            ),
            WorkspaceMember.membership_status == "active",
            User.is_active.is_(True),
        )
        .distinct()
        .order_by(User.full_name.asc(), User.id.asc())
        .all()
    )

    return workspace_users