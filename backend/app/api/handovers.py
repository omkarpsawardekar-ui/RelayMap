from datetime import datetime, timezone
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.user import User
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_item import KnowledgeItem
from app.models.knowledge_relationship import KnowledgeRelationship
from app.models.handover_report import HandoverReport

from app.schemas.handover_report import (
    HandoverGenerateRequest,
    HandoverReviewRequest,
    HandoverReportRead,
)


router = APIRouter(
    prefix="/api/projects/{project_id}/handovers",
    tags=["Handovers"],
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def get_field(obj, *field_names, default=None):
    """
    Safely read the first available attribute from a model.
    This also makes source-reference handling tolerant
    of slightly different chunk ID field names.
    """
    for field_name in field_names:
        if hasattr(obj, field_name):
            value = getattr(obj, field_name)
            if value is not None:
                return value

    return default


def get_user_label(user):
    """
    Return a readable user label without exposing email addresses.
    """
    if user is None:
        return "Unknown user"

    full_name = get_field(user, "full_name", "name", "username")

    if full_name:
        return str(full_name)

    first_name = get_field(user, "first_name")
    last_name = get_field(user, "last_name")

    combined_name = " ".join(
        str(part)
        for part in [first_name, last_name]
        if part
    ).strip()

    if combined_name:
        return combined_name

    return f"User #{user.id}"


def get_project_memberships(db: Session, project_id: int):
    return (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id)
        .all()
    )


def require_project_admin(
    memberships,
    user_id: int,
):
    """
    Development-stage permission check.

    Only an active project owner or admin can generate
    or approve a handover report.
    """
    membership = next(
        (
            member
            for member in memberships
            if member.user_id == user_id
        ),
        None,
    )

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this project.",
        )

    if membership.membership_status != "active":
        raise HTTPException(
            status_code=403,
            detail="Only active project members can perform this action.",
        )

    if membership.role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Only project owners and admins can perform this action.",
        )

    return membership


def build_source_reference(
    item,
    chunks_by_id,
    documents_by_id,
):
    """
    Build an evidence reference for a knowledge item.
    The source excerpt is included as evidence, not
    rewritten as a new claim.
    """
    chunk_id = get_field(
        item,
        "chunk_id",
        "document_chunk_id",
        "source_chunk_id",
    )

    chunk = chunks_by_id.get(chunk_id) if chunk_id else None

    document_id = get_field(item, "document_id")

    if document_id is None and chunk is not None:
        document_id = get_field(chunk, "document_id")

    document = (
        documents_by_id.get(document_id)
        if document_id is not None
        else None
    )

    return {
        "document_id": document_id,
        "document_name": (
            get_field(document, "original_filename")
            if document is not None
            else None
        ),
        "chunk_id": chunk_id,
        "source_locator": (
            get_field(chunk, "source_locator")
            if chunk is not None
            else None
        ),
        "excerpt": get_field(
            item,
            "source_excerpt",
            "evidence_excerpt",
        ),
        "evidence_hash": get_field(item, "evidence_hash"),
    }


def serialize_knowledge_item(
    item,
    chunks_by_id,
    documents_by_id,
    user_labels,
):
    assigned_user_id = get_field(item, "assigned_to_user_id")

    return {
        "id": item.id,
        "type": get_field(item, "item_type"),
        "title": get_field(item, "title"),
        "description": get_field(item, "description"),
        "work_status": get_field(item, "work_status", default="unknown"),
        "assigned_to_user_id": assigned_user_id,
        "assigned_to": (
            user_labels.get(
                assigned_user_id,
                f"User #{assigned_user_id}",
            )
            if assigned_user_id is not None
            else None
        ),
        "candidate_owner_mention": get_field(
            item,
            "candidate_owner_mention",
        ),
        "evidence": build_source_reference(
            item,
            chunks_by_id,
            documents_by_id,
        ),
    }


# ---------------------------------------------------------
# Generate a handover draft
# ---------------------------------------------------------

@router.post(
    "",
    response_model=HandoverReportRead,
    status_code=201,
)
def generate_handover(
    project_id: int,
    request: HandoverGenerateRequest,
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id)
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    memberships = get_project_memberships(db, project_id)

    # Only an active owner/admin can generate the report.
    require_project_admin(
        memberships,
        request.generated_by_user_id,
    )

    # Validate the intended recipient, when supplied.
    if request.recipient_user_id is not None:
        recipient_membership = next(
            (
                member
                for member in memberships
                if member.user_id == request.recipient_user_id
            ),
            None,
        )

        if recipient_membership is None:
            raise HTTPException(
                status_code=400,
                detail="The recipient is not a member of this project.",
            )

        if recipient_membership.membership_status != "active":
            raise HTTPException(
                status_code=400,
                detail="The recipient must be an active project member.",
            )

    # -----------------------------------------------------
    # Load all knowledge records for quality statistics.
    # Only approved items will appear as factual content.
    # -----------------------------------------------------

    all_items = (
        db.query(KnowledgeItem)
        .filter(KnowledgeItem.project_id == project_id)
        .all()
    )

    review_counts = Counter(
        get_field(item, "review_status", default="unknown")
        for item in all_items
    )

    approved_items = [
        item
        for item in all_items
        if get_field(item, "review_status") == "approved"
    ]

    approved_item_ids = {
        item.id
        for item in approved_items
    }

    # -----------------------------------------------------
    # Load approved relationships only.
    # Both endpoints must also be approved knowledge items.
    # -----------------------------------------------------

    all_relationships = (
        db.query(KnowledgeRelationship)
        .filter(
            KnowledgeRelationship.project_id == project_id,
            KnowledgeRelationship.review_status == "approved",
        )
        .all()
    )

    approved_relationships = [
        relationship
        for relationship in all_relationships
        if (
            relationship.source_item_id in approved_item_ids
            and relationship.target_item_id in approved_item_ids
        )
    ]

    # -----------------------------------------------------
    # Load evidence chunks and documents.
    # -----------------------------------------------------

    chunk_ids = set()

    for item in approved_items:
        chunk_id = get_field(
            item,
            "chunk_id",
            "document_chunk_id",
            "source_chunk_id",
        )

        if chunk_id is not None:
            chunk_ids.add(chunk_id)

    for relationship in approved_relationships:
        evidence_chunk_id = get_field(
            relationship,
            "evidence_chunk_id",
        )

        if evidence_chunk_id is not None:
            chunk_ids.add(evidence_chunk_id)

    chunks = []

    if chunk_ids:
        chunks = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.id.in_(chunk_ids))
            .all()
        )

    chunks_by_id = {
        chunk.id: chunk
        for chunk in chunks
    }

    document_ids = {
        get_field(chunk, "document_id")
        for chunk in chunks
        if get_field(chunk, "document_id") is not None
    }

    for item in approved_items:
        document_id = get_field(item, "document_id")

        if document_id is not None:
            document_ids.add(document_id)

    documents = []

    if document_ids:
        documents = (
            db.query(Document)
            .filter(Document.id.in_(document_ids))
            .all()
        )

    documents_by_id = {
        document.id: document
        for document in documents
    }

    # -----------------------------------------------------
    # Load user labels for project members and assignments.
    # -----------------------------------------------------

    user_ids = {
        member.user_id
        for member in memberships
    }

    for item in approved_items:
        assigned_user_id = get_field(item, "assigned_to_user_id")

        if assigned_user_id is not None:
            user_ids.add(assigned_user_id)

    if request.recipient_user_id is not None:
        user_ids.add(request.recipient_user_id)

    user_ids.add(request.generated_by_user_id)

    users = []

    if user_ids:
        users = (
            db.query(User)
            .filter(User.id.in_(user_ids))
            .all()
        )

    users_by_id = {
        user.id: user
        for user in users
    }

    user_labels = {
        user_id: get_user_label(users_by_id.get(user_id))
        for user_id in user_ids
    }

    # -----------------------------------------------------
    # Team snapshot
    # -----------------------------------------------------

    team_snapshot = []

    membership_status_by_user = {}

    for membership in memberships:
        user_id = membership.user_id
        membership_status = membership.membership_status

        membership_status_by_user[user_id] = membership_status

        team_snapshot.append({
            "user_id": user_id,
            "name": user_labels.get(
                user_id,
                f"User #{user_id}",
            ),
            "role": membership.role,
            "membership_status": membership_status,
        })

    # -----------------------------------------------------
    # Serialize approved knowledge.
    # -----------------------------------------------------

    serialized_items = {
        item.id: serialize_knowledge_item(
            item,
            chunks_by_id,
            documents_by_id,
            user_labels,
        )
        for item in approved_items
    }

    # All unfinished approved work.
    unfinished_statuses = {
        "open",
        "in_progress",
        "blocked",
    }

    open_work_items = [
        serialized_items[item.id]
        for item in approved_items
        if get_field(item, "work_status", default="unknown")
        in unfinished_statuses
    ]

    # Only unfinished approved items assigned to departing
    # or departed members are continuity gaps.
    continuity_gaps = [
        serialized_items[item.id]
        for item in approved_items
        if (
            get_field(item, "work_status", default="unknown")
            in unfinished_statuses
            and get_field(item, "assigned_to_user_id") is not None
            and membership_status_by_user.get(
                get_field(item, "assigned_to_user_id")
            ) in ["departing", "departed"]
        )
    ]

    # Approved questions remain visible as unresolved questions.
    unresolved_questions = [
        serialized_items[item.id]
        for item in approved_items
        if get_field(item, "item_type") == "question"
    ]

    # -----------------------------------------------------
    # Approved relationships.
    # -----------------------------------------------------

    relationship_data = []

    for relationship in approved_relationships:
        relationship_data.append({
            "id": relationship.id,
            "source_item_id": relationship.source_item_id,
            "source_title": serialized_items[
                relationship.source_item_id
            ]["title"],
            "target_item_id": relationship.target_item_id,
            "target_title": serialized_items[
                relationship.target_item_id
            ]["title"],
            "relationship_type": relationship.relation_type,
            "evidence_excerpt": get_field(
                relationship,
                "evidence_excerpt",
            ),
            "evidence_hash": get_field(
                relationship,
                "evidence_hash",
            ),
            "evidence_chunk_id": get_field(
                relationship,
                "evidence_chunk_id",
            ),
        })

    # -----------------------------------------------------
    # Quality notes and limitations.
    # -----------------------------------------------------

    quality_notes = [
        (
            "Only approved knowledge items and approved relationships "
            "are included as factual project knowledge."
        ),
        (
            "Pending, rejected, and needs-clarification records are "
            "excluded from the factual sections of this report."
        ),
        (
            "This is a generated draft. A project owner or admin "
            "must review it before it is approved for handover."
        ),
        (
            "An unknown work status is not treated as completed."
        ),
    ]

    if not approved_items:
        quality_notes.append(
            "No approved knowledge items were available when this "
            "draft was generated. The report may therefore be incomplete."
        )

    if not continuity_gaps:
        quality_notes.append(
            "No approved unfinished items assigned to departing or "
            "departed members were found in the current project records."
        )

    if review_counts.get("pending", 0) > 0:
        quality_notes.append(
            f"{review_counts['pending']} knowledge records are still pending review."
        )

    if review_counts.get("needs_clarification", 0) > 0:
        quality_notes.append(
            f"{review_counts['needs_clarification']} knowledge records "
            "need clarification."
        )

    if review_counts.get("rejected", 0) > 0:
        quality_notes.append(
            f"{review_counts['rejected']} knowledge records were rejected "
            "and are excluded from this report."
        )

    # Recommendations are clearly separated from evidence-backed facts.
    recommended_next_steps = []

    if continuity_gaps:
        recommended_next_steps.append(
            "Review each continuity gap and assign an active successor."
        )

    if open_work_items:
        recommended_next_steps.append(
            "Confirm the current status and next action for each unfinished item."
        )

    if unresolved_questions:
        recommended_next_steps.append(
            "Resolve the listed open questions with the relevant project members."
        )

    if not recommended_next_steps:
        recommended_next_steps.append(
            "Ask the successor to review the approved project knowledge "
            "and confirm that the handover is complete."
        )

    # -----------------------------------------------------
    # Final report snapshot.
    # -----------------------------------------------------

    generated_at = datetime.now(timezone.utc)

    project_name = get_field(
        project,
        "name",
        "title",
        default=f"Project #{project_id}",
    )

    recipient_label = None

    if request.recipient_user_id is not None:
        recipient_label = user_labels.get(
            request.recipient_user_id,
            f"User #{request.recipient_user_id}",
        )

    report_data = {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),

        "project": {
            "id": project_id,
            "name": project_name,
        },

        "recipient": {
            "user_id": request.recipient_user_id,
            "name": recipient_label,
        },

        "generated_by": {
            "user_id": request.generated_by_user_id,
            "name": user_labels.get(
                request.generated_by_user_id,
                f"User #{request.generated_by_user_id}",
            ),
        },

        "summary": {
            "team_members": len(team_snapshot),
            "source_documents_referenced": len(documents_by_id),
            "approved_knowledge_items": len(approved_items),
            "approved_relationships": len(relationship_data),
            "unfinished_work_items": len(open_work_items),
            "continuity_gaps": len(continuity_gaps),
            "unresolved_questions": len(unresolved_questions),
            "pending_knowledge_records": review_counts.get("pending", 0),
            "needs_clarification_records": review_counts.get(
                "needs_clarification",
                0,
            ),
            "rejected_knowledge_records": review_counts.get(
                "rejected",
                0,
            ),
        },

        "team_snapshot": team_snapshot,

        "approved_knowledge": list(serialized_items.values()),

        "open_work_items": open_work_items,

        "continuity_gaps": continuity_gaps,

        "approved_relationships": relationship_data,

        "unresolved_questions": unresolved_questions,

        "recommended_next_steps": recommended_next_steps,

        "quality_and_limitations": quality_notes,
    }

    report = HandoverReport(
        project_id=project_id,
        recipient_user_id=request.recipient_user_id,
        generated_by_user_id=request.generated_by_user_id,
        title=f"Handover Report - {project_name}",
        report_data=report_data,
        status="draft",
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    return report


# ---------------------------------------------------------
# List handover reports
# ---------------------------------------------------------

@router.get(
    "",
    response_model=list[HandoverReportRead],
)
def list_handovers(
    project_id: int,
    db: Session = Depends(get_db),
):
    return (
        db.query(HandoverReport)
        .filter(HandoverReport.project_id == project_id)
        .order_by(HandoverReport.created_at.desc())
        .all()
    )


# ---------------------------------------------------------
# Get one handover report
# ---------------------------------------------------------

@router.get(
    "/{report_id}",
    response_model=HandoverReportRead,
)
def get_handover(
    project_id: int,
    report_id: int,
    db: Session = Depends(get_db),
):
    report = (
        db.query(HandoverReport)
        .filter(
            HandoverReport.id == report_id,
            HandoverReport.project_id == project_id,
        )
        .first()
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Handover report not found.",
        )

    return report


# ---------------------------------------------------------
# Approve or reject a handover report
# ---------------------------------------------------------

@router.patch(
    "/{report_id}/review",
    response_model=HandoverReportRead,
)
def review_handover(
    project_id: int,
    report_id: int,
    request: HandoverReviewRequest,
    db: Session = Depends(get_db),
):
    memberships = get_project_memberships(db, project_id)

    require_project_admin(
        memberships,
        request.reviewer_user_id,
    )

    report = (
        db.query(HandoverReport)
        .filter(
            HandoverReport.id == report_id,
            HandoverReport.project_id == project_id,
        )
        .first()
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Handover report not found.",
        )

    if report.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=(
                "Only draft reports can be reviewed. "
                "This report has already been reviewed."
            ),
        )

    report.status = request.decision
    report.reviewed_by_user_id = request.reviewer_user_id
    report.reviewed_at = datetime.now(timezone.utc)
    report.review_notes = request.review_notes

    db.commit()
    db.refresh(report)

    return report