
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_current_user

from app.core.permissions import (
    require_project_access,
    require_project_management,
)

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

from sqlalchemy import or_

from app.core.dependencies import get_current_user
from app.core.permissions import require_project_access

from app.models import KnowledgeRelationship

from app.services.llm_continuity_service import (
    explain_continuity_risks,
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
    current_user: User = Depends(get_current_user),
):
    """
    Mark a project member active, departing or departed.

    Only authenticated project owners/admins or workspace
    owners/admins can change a member's transition status.

    This updates project membership only. It does not deactivate
    the user globally or automatically reassign their work.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    # Verify the authenticated user has project management access.
    require_project_management(
        db,
        project,
        current_user.id,
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
    current_user: User = Depends(get_current_user),
):
    """
    Find approved, unfinished knowledge items assigned to
    project members whose membership is departing or departed.

    Only human-approved knowledge records are considered.
    No work is automatically reassigned.

    Only active project members and workspace owners/admins
    can inspect continuity gaps.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    # Verify that the authenticated user can view this project.
    require_project_access(
        db,
        project,
        current_user.id,
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


# --------------------------------------------------
# AI-POWERED CONTINUITY RISK EXPLANATIONS
# --------------------------------------------------

@router.post("/gaps/explain")
def explain_project_continuity_gaps(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Explain existing continuity gaps using Groq AI.

    Only approved knowledge and approved relationships are used.
    The AI provides advisory explanations; no project state,
    assignment or review decision is modified.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    require_project_access(
        db,
        project,
        current_user.id,
    )

    # Find departing/departed project members.
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
        return {
            "project_id": project_id,
            "model": "openai/gpt-oss-120b",
            "potential_gaps_count": 0,
            "gaps_analyzed": 0,
            "explanations": [],
            "message": (
                "No departing or departed project members were found."
            ),
        }

    departing_user_ids = list(member_lookup.keys())

    # Recalculate potential gaps from approved project records.
    gap_rows = (
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

    if not gap_rows:
        return {
            "project_id": project_id,
            "model": "openai/gpt-oss-120b",
            "potential_gaps_count": 0,
            "gaps_analyzed": 0,
            "explanations": [],
            "message": (
                "No approved unfinished work assigned to departing "
                "or departed members was found."
            ),
        }

    # Limit the number of gaps sent in one free-tier API request.
    gaps_to_analyze = gap_rows[:10]

    gap_item_ids = [
        item.id
        for item, document, chunk in gaps_to_analyze
    ]

    # Retrieve only approved relationships connected to these gaps.
    relationship_rows = (
        db.query(
            KnowledgeRelationship,
            DocumentChunk,
            Document,
        )
        .join(
            DocumentChunk,
            DocumentChunk.id
            == KnowledgeRelationship.evidence_chunk_id,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .filter(
            KnowledgeRelationship.project_id == project_id,
            KnowledgeRelationship.review_status == "approved",
            or_(
                KnowledgeRelationship.source_item_id.in_(
                    gap_item_ids
                ),
                KnowledgeRelationship.target_item_id.in_(
                    gap_item_ids
                ),
            ),
        )
        .order_by(KnowledgeRelationship.id.asc())
        .all()
    )

    related_item_ids = set()

    for relationship, evidence_chunk, evidence_document in relationship_rows:
        related_item_ids.add(relationship.source_item_id)
        related_item_ids.add(relationship.target_item_id)

    # Ensure both ends of every relationship are approved records.
    related_items = []

    if related_item_ids:
        related_items = (
            db.query(KnowledgeItem)
            .filter(
                KnowledgeItem.project_id == project_id,
                KnowledgeItem.id.in_(related_item_ids),
                KnowledgeItem.review_status == "approved",
            )
            .all()
        )

    approved_item_lookup = {
        item.id: item
        for item in related_items
    }

    relationships_by_gap = {
        item_id: []
        for item_id in gap_item_ids
    }

    for relationship, evidence_chunk, evidence_document in relationship_rows:

        source_item = approved_item_lookup.get(
            relationship.source_item_id
        )

        target_item = approved_item_lookup.get(
            relationship.target_item_id
        )

        if source_item is None or target_item is None:
            continue

        excerpt = relationship.evidence_excerpt or ""

        # Recheck source evidence before sending it to the model.
        if not excerpt or excerpt not in evidence_chunk.chunk_text:
            continue

        relationship_context = {
            "relationship_id": relationship.id,
            "relation_type": relationship.relation_type,
            "source_item": {
                "id": source_item.id,
                "title": source_item.title,
            },
            "target_item": {
                "id": target_item.id,
                "title": target_item.title,
            },
            "evidence": {
                "filename": evidence_document.original_filename,
                "locator": evidence_chunk.source_locator,
                "excerpt": excerpt,
            },
        }

        if relationship.source_item_id in relationships_by_gap:
            relationships_by_gap[
                relationship.source_item_id
            ].append(relationship_context)

        if relationship.target_item_id in relationships_by_gap:
            relationships_by_gap[
                relationship.target_item_id
            ].append(relationship_context)

    # Build compact, evidence-first prompts for the AI.
    risk_contexts = []
    evidence_by_gap = {}

    for item, document, chunk in gaps_to_analyze:

        member = member_lookup[item.assigned_to_user_id]

        connected_relationships = relationships_by_gap.get(
            item.id,
            [],
        )[:8]

        signals = [
            "The knowledge record has been approved by a human reviewer.",
            f"The recorded work status is {item.work_status}.",
            (
                f"The assigned member is marked "
                f"{member['status']}."
            ),
            "No successor is recorded on this knowledge item.",
        ]

        if connected_relationships:
            signals.append(
                f"{len(connected_relationships)} approved relationship "
                "record(s) connect this item to other approved work."
            )
        else:
            signals.append(
                "No approved relationship to other work was found "
                "in the records supplied for this analysis."
            )

        risk_contexts.append({
            "knowledge_item_id": item.id,
            "title": item.title,
            "item_type": item.item_type,
            "work_status": item.work_status,
            "assigned_member": {
                "name": member["name"],
                "membership_status": member["status"],
            },
            "signals": signals,
            "primary_evidence": {
                "filename": document.original_filename,
                "locator": chunk.source_locator,
                "excerpt": item.source_excerpt,
            },
            "approved_relationships": connected_relationships,
        })

        evidence_by_gap[item.id] = [
            {
                "kind": "approved_knowledge_item",
                "record_id": item.id,
                "filename": document.original_filename,
                "locator": chunk.source_locator,
                "excerpt": item.source_excerpt,
            }
        ] + [
            {
                "kind": "approved_relationship",
                "relationship_id": relation["relationship_id"],
                "relation_type": relation["relation_type"],
                "source_item": relation["source_item"],
                "target_item": relation["target_item"],
                "filename": relation["evidence"]["filename"],
                "locator": relation["evidence"]["locator"],
                "excerpt": relation["evidence"]["excerpt"],
            }
            for relation in connected_relationships
        ]

    try:
        ai_results = explain_continuity_risks(
            risk_contexts
        )

    except RuntimeError as exc:
        logger.exception(
            "Continuity AI analysis failed for project %s.",
            project_id,
        )

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    ai_by_id = {
        result["knowledge_item_id"]: result
        for result in ai_results
    }

    explanations = []

    for context in risk_contexts:
        item_id = context["knowledge_item_id"]
        analysis = ai_by_id.get(item_id)

        if analysis is None:
            continue

        explanations.append({
            **analysis,
            "title": context["title"],
            "assigned_member": context["assigned_member"],
            "work_status": context["work_status"],
            "attention_signals": context["signals"],
            "evidence": evidence_by_gap[item_id],
            "review_status": "advisory",
        })

    return {
        "project_id": project_id,
        "model": "openai/gpt-oss-120b",
        "potential_gaps_count": len(gap_rows),
        "gaps_analyzed": len(explanations),
        "analysis_limit": 10,
        "more_gaps_available": len(gap_rows) > 10,
        "explanations": explanations,
        "message": (
            "AI explanations are advisory. Verify their evidence "
            "and decide the appropriate handover action."
        ),
    }