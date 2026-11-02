
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models import (
    Project,
    ProjectMember,
    User,
    KnowledgeItem,
    Document,
    DocumentChunk,
)

from app.schemas.continuity import (
    MemberStatusUpdate,
    MemberStatusResult,
    ContinuityGapItem,
    ContinuityGapReport,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/continuity",
    tags=["Continuity Intelligence"],
)


# --------------------------------------------------
# UPDATE PROJECT MEMBER STATUS
# --------------------------------------------------

@router.patch(
    "/members/{user_id}/status",
    response_model=MemberStatusResult,
)
def update_member_status(
    project_id: int,
    user_id: int,
    payload: MemberStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    Mark a project member active, departing or departed.

    This updates project membership only. It does not deactivate
    the user globally or automatically reassign their work.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    member = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        .first()
    )

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="This user is not a member of the project.",
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found.",
        )

    member.membership_status = payload.membership_status

    try:
        db.commit()
        db.refresh(member)

    except Exception as exc:
        db.rollback()

        logger.exception(
            "Could not update project member status."
        )

        raise HTTPException(
            status_code=500,
            detail="Could not update membership status.",
        ) from exc

    return MemberStatusResult(
        project_id=project_id,
        user_id=user.id,
        full_name=user.full_name,
        role=member.role,
        membership_status=member.membership_status,
    )


# --------------------------------------------------
# DETECT POTENTIAL OWNERSHIP GAPS
# --------------------------------------------------

@router.get(
    "/gaps",
    response_model=ContinuityGapReport,
)
def detect_continuity_gaps(
    project_id: int,
    db: Session = Depends(get_db),
):
    """
    Find approved, unfinished knowledge items assigned to
    project members whose membership is departing or departed.

    Only human-approved knowledge records are considered.
    No work is automatically reassigned.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    # Find members who are leaving or have left.
    member_rows = (
        db.query(ProjectMember, User)
        .join(
            User,
            User.id == ProjectMember.user_id,
        )
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.membership_status.in_(
                ["departing", "departed"]
            ),
        )
        .all()
    )

    member_lookup = {
        member.user_id: {
            "name": user.full_name,
            "status": member.membership_status,
        }
        for member, user in member_rows
    }

    if not member_lookup:
        return ContinuityGapReport(
            project_id=project_id,
            departing_members_count=0,
            potential_gaps_count=0,
            gaps=[],
        )

    departing_user_ids = list(member_lookup.keys())

    # Inspect only approved records that represent unfinished work.
    # Pending or rejected extractions are not treated as established facts.
    results = (
        db.query(
            KnowledgeItem,
            Document,
            DocumentChunk,
        )
        .join(
            Document,
            Document.id == KnowledgeItem.document_id,
        )
        .join(
            DocumentChunk,
            DocumentChunk.id == KnowledgeItem.chunk_id,
        )
        .filter(
            KnowledgeItem.project_id == project_id,
            KnowledgeItem.assigned_to_user_id.in_(
                departing_user_ids
            ),
            KnowledgeItem.review_status == "approved",
            KnowledgeItem.work_status.in_(
                ["open", "in_progress", "blocked"]
            ),
        )
        .order_by(KnowledgeItem.id.asc())
        .all()
    )

    gaps = []

    for item, document, chunk in results:

        member = member_lookup[item.assigned_to_user_id]

        gaps.append(
            ContinuityGapItem(
                knowledge_item_id=item.id,
                item_type=item.item_type,
                title=item.title,
                work_status=item.work_status,

                assigned_member_user_id=item.assigned_to_user_id,
                assigned_member_name=member["name"],
                membership_status=member["status"],

                document_id=document.id,
                original_filename=document.original_filename,
                source_locator=chunk.source_locator,
                source_excerpt=item.source_excerpt,

                reason=(
                    "This approved, unfinished item is still assigned "
                    "to a project member marked as departing or departed. "
                    "No successor is recorded on this item."
                ),
            )
        )

    return ContinuityGapReport(
        project_id=project_id,
        departing_members_count=len(member_lookup),
        potential_gaps_count=len(gaps),
        gaps=gaps,
    )