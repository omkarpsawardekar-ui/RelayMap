
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import (
    get_workspace_membership,
    get_project_membership,
    require_project_access,
    require_project_management
)

from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.workspace_member import WorkspaceMember
from app.models.user import User

from app.schemas.project import ProjectCreate, ProjectRead
from app.schemas.project_member import (
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectMemberDetails
)


router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"]
)


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED
)
def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a project inside a workspace owned or administered by the user."""

    if project_data.workspace_id is not None:
        workspace_id = project_data.workspace_id
    else:
        # Backwards compatibility for the existing frontend:
        # automatically select the user's only manageable workspace.
        memberships = db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == current_user.id,
            WorkspaceMember.membership_status == "active",
            WorkspaceMember.role.in_(["owner", "admin"])
        ).all()

        if len(memberships) == 0:
            raise HTTPException(
                status_code=403,
                detail="Create a workspace or obtain workspace admin access first"
            )

        if len(memberships) > 1:
            raise HTTPException(
                status_code=422,
                detail="Please select a workspace when creating a project"
            )

        workspace_id = memberships[0].workspace_id

    workspace_membership = get_workspace_membership(
        db,
        workspace_id,
        current_user.id
    )

    if (
        workspace_membership is None
        or workspace_membership.role not in ("owner", "admin")
    ):
        raise HTTPException(
            status_code=403,
            detail="Only workspace owners and admins can create projects"
        )

    new_project = Project(
        name=project_data.name.strip(),
        description=project_data.description,
        workspace_id=workspace_id,
        created_by=current_user.id,
        status="active"
    )

    try:
        db.add(new_project)
        db.flush()

        owner_membership = ProjectMember(
            project_id=new_project.id,
            user_id=current_user.id,
            role="owner",
            responsibility="Project ownership",
            membership_status="active"
        )

        db.add(owner_membership)
        db.commit()
        db.refresh(new_project)

    except Exception:
        db.rollback()
        raise

    return new_project


@router.get("", response_model=list[ProjectRead])
def get_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List only projects accessible to the current user."""

    workspace_admin_access = db.query(
        WorkspaceMember.id
    ).filter(
        WorkspaceMember.workspace_id == Project.workspace_id,
        WorkspaceMember.user_id == current_user.id,
        WorkspaceMember.membership_status == "active",
        WorkspaceMember.role.in_(["owner", "admin"])
    ).exists()

    project_member_access = db.query(
        ProjectMember.id
    ).filter(
        ProjectMember.project_id == Project.id,
        ProjectMember.user_id == current_user.id,
        ProjectMember.membership_status == "active"
    ).exists()

    return (
        db.query(Project)
        .filter(
            or_(
                workspace_admin_access,
                project_member_access
            )
        )
        .order_by(Project.created_at.desc())
        .all()
    )


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = db.query(Project).filter(
        Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    require_project_access(db, project, current_user.id)

    return project


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberRead,
    status_code=status.HTTP_201_CREATED
)
def add_project_member(
    project_id: int,
    member_data: ProjectMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = db.query(Project).filter(
        Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    require_project_management(
        db,
        project,
        current_user.id
    )

    user = db.query(User).filter(
        User.id == member_data.user_id,
        User.is_active.is_(True)
    ).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # A user must first be a member of the workspace.
    workspace_membership = get_workspace_membership(
        db,
        project.workspace_id,
        user.id
    )

    if workspace_membership is None:
        raise HTTPException(
            status_code=409,
            detail="Invite this user to the workspace before adding them to a project"
        )

    existing_member = db.query(ProjectMember).filter(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == member_data.user_id
    ).first()

    if existing_member:
        raise HTTPException(
            status_code=409,
            detail="User is already a member of this project"
        )

    new_member = ProjectMember(
        project_id=project_id,
        user_id=member_data.user_id,
        role=member_data.role,
        responsibility=member_data.responsibility,
        membership_status="active"
    )

    try:
        db.add(new_member)
        db.commit()
        db.refresh(new_member)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not add this project member"
        )

    return new_member


@router.get(
    "/{project_id}/members",
    response_model=list[ProjectMemberDetails]
)
def get_project_members(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    project = db.query(Project).filter(
        Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    require_project_access(db, project, current_user.id)

    results = (
        db.query(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.membership_status == "active"
        )
        .order_by(ProjectMember.id)
        .all()
    )

    return [
        ProjectMemberDetails(
            id=member.id,
            project_id=member.project_id,
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=member.role,
            responsibility=member.responsibility,
            membership_status=member.membership_status,
            joined_at=member.joined_at
        )
        for member, user in results
    ]