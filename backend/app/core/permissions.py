from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.workspace_member import WorkspaceMember


def get_workspace_membership(
    db: Session,
    workspace_id: int,
    user_id: int
):
    return db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
        WorkspaceMember.membership_status == "active"
    ).first()


def get_project_membership(
    db: Session,
    project_id: int,
    user_id: int
):
    return db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == user_id,
        ProjectMember.membership_status == "active"
    ).first()


def require_project_access(
    db: Session,
    project: Project,
    user_id: int
):
    """Allow active project members and workspace owners/admins."""

    workspace_membership = get_workspace_membership(
        db,
        project.workspace_id,
        user_id
    )

    if workspace_membership is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    if workspace_membership.role in ("owner", "admin"):
        return workspace_membership

    project_membership = get_project_membership(
        db,
        project.id,
        user_id
    )

    if project_membership is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    return project_membership


def require_project_write_access(
    db: Session,
    project: Project,
    user_id: int
):
    """Allow workspace admins and project owners/admins/members."""

    workspace_membership = get_workspace_membership(
        db,
        project.workspace_id,
        user_id
    )

    if workspace_membership is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    if workspace_membership.role in ("owner", "admin"):
        return workspace_membership

    project_membership = get_project_membership(
        db,
        project.id,
        user_id
    )

    if project_membership is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    if project_membership.role not in ("owner", "admin", "member"):
        raise HTTPException(
            status_code=403,
            detail="You have read-only access to this project"
        )

    return project_membership


def require_project_management(
    db: Session,
    project: Project,
    user_id: int
):
    """Allow workspace owners/admins and project owners/admins."""

    workspace_membership = get_workspace_membership(
        db,
        project.workspace_id,
        user_id
    )

    if workspace_membership is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    if workspace_membership.role in ("owner", "admin"):
        return workspace_membership

    project_membership = get_project_membership(
        db,
        project.id,
        user_id
    )

    if (
        project_membership is None
        or project_membership.role not in ("owner", "admin")
    ):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to manage this project"
        )

    return project_membership