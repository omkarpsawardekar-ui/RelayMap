
import hashlib
import re
import secrets

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.session import get_db

from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.models.workspace_invitation import WorkspaceInvitation

from app.schemas.workspace import WorkspaceCreate, WorkspaceRead

from app.schemas.workspace_invitation import (
    WorkspaceInvitationCreate,
    WorkspaceInvitationCreated,
    WorkspaceInvitationRead,
    WorkspaceInvitationAccept,
    WorkspaceInvitationAcceptResponse,
    WorkspaceInvitationInboxItem
)


router = APIRouter(
    prefix="/api/workspaces",
    tags=["Workspaces"]
)


def get_active_workspace_membership(
    db: Session,
    workspace_id: int,
    user_id: int
):
    return db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
        WorkspaceMember.membership_status == "active"
    ).first()


def require_workspace_admin(
    db: Session,
    workspace_id: int,
    user_id: int
):
    membership = get_active_workspace_membership(
        db,
        workspace_id,
        user_id
    )

    if membership is None or membership.role not in ("owner", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Only workspace owners and admins can perform this action"
        )

    return membership


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post(
    "",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED
)
def create_workspace(
    data: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    name = data.name.strip()

    if len(name) < 2:
        raise HTTPException(
            status_code=422,
            detail="Workspace name must contain at least 2 characters"
        )

    workspace = Workspace(
        name=name,
        description=data.description,
        created_by=current_user.id
    )

    try:
        db.add(workspace)
        db.flush()

        db.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=current_user.id,
                role="owner",
                membership_status="active"
            )
        )

        db.commit()
        db.refresh(workspace)

    except Exception:
        db.rollback()
        raise

    return workspace


@router.get(
    "/invitations/mine",
    response_model=list[WorkspaceInvitationInboxItem]
)
def get_my_invitations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Show pending workspace invitations addressed to the logged-in user.
    The recipient does not need to be a workspace member yet.
    """

    now = datetime.now(timezone.utc)

    results = (
        db.query(WorkspaceInvitation, Workspace)
        .join(
            Workspace,
            Workspace.id == WorkspaceInvitation.workspace_id
        )
        .filter(
            WorkspaceInvitation.invited_email == current_user.email.strip().lower(),
            WorkspaceInvitation.status == "pending",
            WorkspaceInvitation.expires_at > now
        )
        .order_by(WorkspaceInvitation.created_at.desc())
        .all()
    )

    return [
        {
            "id": invitation.id,
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "invited_email": invitation.invited_email,
            "role": invitation.role,
            "status": invitation.status,
            "created_at": invitation.created_at,
            "expires_at": invitation.expires_at
        }
        for invitation, workspace in results
    ]


@router.post(
    "/invitations/{invitation_id}/accept",
    response_model=WorkspaceInvitationAcceptResponse
)
def accept_invitation_from_inbox(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Accept an invitation from the inbox.

    Access is restricted to the authenticated account whose email
    was invited. The raw invitation token is not needed here.
    """

    invitation = db.query(WorkspaceInvitation).filter(
        WorkspaceInvitation.id == invitation_id,
        WorkspaceInvitation.invited_email == current_user.email.strip().lower()
    ).first()

    if invitation is None:
        raise HTTPException(
            status_code=404,
            detail="Invitation not found for your account"
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"This invitation is {invitation.status}"
        )

    now = datetime.now(timezone.utc)
    expires_at = invitation.expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        invitation.status = "expired"
        db.commit()

        raise HTTPException(
            status_code=410,
            detail="This invitation has expired"
        )

    if not current_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account is inactive"
        )

    workspace = db.query(Workspace).filter(
        Workspace.id == invitation.workspace_id
    ).first()

    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace no longer exists"
        )

    existing_membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace.id,
        WorkspaceMember.user_id == current_user.id
    ).first()

    try:
        if existing_membership:
            if existing_membership.membership_status == "active":
                raise HTTPException(
                    status_code=409,
                    detail="You are already a member of this workspace"
                )

            existing_membership.role = invitation.role
            existing_membership.membership_status = "active"

        else:
            db.add(
                WorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=current_user.id,
                    role=invitation.role,
                    membership_status="active"
                )
            )

        invitation.status = "accepted"
        invitation.accepted_by_user_id = current_user.id
        invitation.accepted_at = now

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise

    return {
        "message": "You successfully joined the workspace.",
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "role": invitation.role
    }

@router.get("", response_model=list[WorkspaceRead])
def get_my_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return (
        db.query(Workspace)
        .join(
            WorkspaceMember,
            WorkspaceMember.workspace_id == Workspace.id
        )
        .filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.membership_status == "active"
        )
        .order_by(Workspace.created_at.desc())
        .all()
    )


@router.post(
    "/invitations/accept",
    response_model=WorkspaceInvitationAcceptResponse
)
def accept_workspace_invitation(
    data: WorkspaceInvitationAccept,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Accept an invitation belonging to the logged-in user's email."""

    token_hash = hash_invitation_token(data.token)

    invitation = db.query(WorkspaceInvitation).filter(
        WorkspaceInvitation.token_hash == token_hash
    ).first()

    if invitation is None:
        raise HTTPException(
            status_code=404,
            detail="Invitation not found or invalid"
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"This invitation is {invitation.status}"
        )

    now = datetime.now(timezone.utc)
    expires_at = invitation.expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        invitation.status = "expired"
        db.commit()

        raise HTTPException(
            status_code=410,
            detail="This invitation has expired"
        )

    if current_user.email.strip().lower() != invitation.invited_email.lower():
        raise HTTPException(
            status_code=403,
            detail="This invitation was sent to a different email address"
        )

    if not current_user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account is inactive"
        )

    workspace = db.query(Workspace).filter(
        Workspace.id == invitation.workspace_id
    ).first()

    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace no longer exists"
        )

    existing_membership = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace.id,
        WorkspaceMember.user_id == current_user.id
    ).first()

    if existing_membership and existing_membership.membership_status == "active":
        invitation.status = "accepted"
        invitation.accepted_by_user_id = current_user.id
        invitation.accepted_at = now
        db.commit()

        return {
            "message": "You are already a member of this workspace.",
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "role": existing_membership.role
        }

    try:
        if existing_membership:
            existing_membership.role = invitation.role
            existing_membership.membership_status = "active"
        else:
            db.add(
                WorkspaceMember(
                    workspace_id=workspace.id,
                    user_id=current_user.id,
                    role=invitation.role,
                    membership_status="active"
                )
            )

        invitation.status = "accepted"
        invitation.accepted_by_user_id = current_user.id
        invitation.accepted_at = now

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "message": "You successfully joined the workspace.",
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "role": invitation.role
    }


@router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    membership = get_active_workspace_membership(
        db,
        workspace_id,
        current_user.id
    )

    if membership is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found"
        )

    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id
    ).first()

    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found"
        )

    return workspace


@router.post(
    "/{workspace_id}/invitations",
    response_model=WorkspaceInvitationCreated,
    status_code=status.HTTP_201_CREATED
)
def create_workspace_invitation(
    workspace_id: int,
    data: WorkspaceInvitationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a seven-day invitation link for a workspace."""

    require_workspace_admin(
        db,
        workspace_id,
        current_user.id
    )

    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id
    ).first()

    if workspace is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found"
        )

    invited_email = data.invited_email.strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", invited_email):
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid email address"
        )

    existing_user = db.query(User).filter(
        User.email == invited_email,
        User.is_active.is_(True)
    ).first()

    if existing_user:
        existing_membership = get_active_workspace_membership(
            db,
            workspace_id,
            existing_user.id
        )

        if existing_membership:
            raise HTTPException(
                status_code=409,
                detail="This user is already a workspace member"
            )

    # Revoke older pending invitations for the same email/workspace.
    previous_invitations = db.query(WorkspaceInvitation).filter(
        WorkspaceInvitation.workspace_id == workspace_id,
        WorkspaceInvitation.invited_email == invited_email,
        WorkspaceInvitation.status == "pending"
    ).all()

    for previous in previous_invitations:
        previous.status = "revoked"

    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_invitation_token(raw_token)

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    invitation = WorkspaceInvitation(
        workspace_id=workspace_id,
        invited_email=invited_email,
        role=data.role,
        token_hash=token_hash,
        invited_by_user_id=current_user.id,
        status="pending",
        expires_at=expires_at
    )

    try:
        db.add(invitation)
        db.commit()
        db.refresh(invitation)

    except Exception:
        db.rollback()
        raise

    invite_url = (
        f"{settings.FRONTEND_BASE_URL.rstrip('/')}"
        f"/?invite={raw_token}"
    )

    return {
        "id": invitation.id,
        "invited_email": invitation.invited_email,
        "role": invitation.role,
        "invite_url": invite_url,
        "status": invitation.status,
        "expires_at": invitation.expires_at
    }


@router.get(
    "/{workspace_id}/invitations",
    response_model=list[WorkspaceInvitationRead]
)
def get_workspace_invitations(
    workspace_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_workspace_admin(
        db,
        workspace_id,
        current_user.id
    )

    return (
        db.query(WorkspaceInvitation)
        .filter(WorkspaceInvitation.workspace_id == workspace_id)
        .order_by(WorkspaceInvitation.created_at.desc())
        .all()
    )


@router.delete("/{workspace_id}/invitations/{invitation_id}")
def revoke_workspace_invitation(
    workspace_id: int,
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_workspace_admin(
        db,
        workspace_id,
        current_user.id
    )

    invitation = db.query(WorkspaceInvitation).filter(
        WorkspaceInvitation.id == invitation_id,
        WorkspaceInvitation.workspace_id == workspace_id
    ).first()

    if invitation is None:
        raise HTTPException(
            status_code=404,
            detail="Invitation not found"
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending invitations can be revoked"
        )

    invitation.status = "revoked"
    db.commit()

    return {
        "message": "Invitation revoked successfully"
    }