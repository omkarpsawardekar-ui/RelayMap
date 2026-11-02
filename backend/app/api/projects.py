
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db

from app.models.project import Project
from app.models.project_member import ProjectMember
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
    db: Session = Depends(get_db)
):

    creator = db.query(User).filter(
        User.id == project_data.created_by,
        User.is_active.is_(True)
    ).first()

    if not creator:
        raise HTTPException(
            status_code=404,
            detail="Project creator not found"
        )

    new_project = Project(
        name=project_data.name.strip(),
        description=project_data.description,
        created_by=project_data.created_by,
        status="active"
    )

    try:
        db.add(new_project)
        db.flush()

        # Automatically add the creator as project owner
        owner_membership = ProjectMember(
            project_id=new_project.id,
            user_id=creator.id,
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
def get_projects(db: Session = Depends(get_db)):

    return db.query(Project).order_by(
        Project.created_at.desc()
    ).all()


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    db: Session = Depends(get_db)
):

    project = db.query(Project).filter(
        Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    return project


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberRead,
    status_code=status.HTTP_201_CREATED
)
def add_project_member(
    project_id: int,
    member_data: ProjectMemberCreate,
    db: Session = Depends(get_db)
):

    project = db.query(Project).filter(
        Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
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
    db: Session = Depends(get_db)
):

    project = db.query(Project).filter(
        Project.id == project_id
    ).first()

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    results = (
        db.query(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .filter(ProjectMember.project_id == project_id)
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