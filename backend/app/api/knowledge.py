
import logging

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models import (
    Project,
    ProjectMember,
    User,
    Document,
    DocumentChunk,
    KnowledgeItem,
)

from app.schemas.knowledge_item import (
    KnowledgeItemRead,
    KnowledgeExtractionSummary,
)

from app.schemas.knowledge_review import (
    KnowledgeReviewUpdate,
    KnowledgeReviewResult,
)

from app.services.knowledge_extraction_service import (
    extract_candidates_from_chunk,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["Knowledge"],
)


# --------------------------------------------------
# EXTRACT KNOWLEDGE FROM A DOCUMENT
# --------------------------------------------------

@router.post(
    "/documents/{document_id}/extract",
    response_model=KnowledgeExtractionSummary,
)
def extract_document_knowledge(
    project_id: int,
    document_id: int,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(404, "Project not found.")

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.project_id == project_id,
        )
        .first()
    )

    if document is None:
        raise HTTPException(404, "Document not found in this project.")

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )

    if not chunks:
        raise HTTPException(
            409,
            "This document has no evidence chunks. Run chunking or backfill first.",
        )

    existing_rows = (
        db.query(
            KnowledgeItem.chunk_id,
            KnowledgeItem.item_type,
            KnowledgeItem.evidence_hash,
        )
        .filter(KnowledgeItem.document_id == document_id)
        .all()
    )

    existing_keys = set(existing_rows)
    seen_keys = set(existing_keys)

    new_items = []
    items_by_type = Counter()
    duplicate_count = 0

    for chunk in chunks:

        candidates = extract_candidates_from_chunk(
            chunk.chunk_text
        )

        for candidate in candidates:

            unique_key = (
                chunk.id,
                candidate["item_type"],
                candidate["evidence_hash"],
            )

            if unique_key in seen_keys:
                duplicate_count += 1
                continue

            seen_keys.add(unique_key)

            new_items.append(
                KnowledgeItem(
                    project_id=project_id,
                    document_id=document_id,
                    chunk_id=chunk.id,
                    item_type=candidate["item_type"],
                    title=candidate["title"],
                    description=candidate["description"],
                    source_excerpt=candidate["source_excerpt"],
                    evidence_hash=candidate["evidence_hash"],
                    candidate_owner_mention=(
                        candidate["candidate_owner_mention"]
                    ),
                    assigned_to_user_id=None,
                    work_status="unknown",
                    review_status="pending",
                    extraction_method="rule_based",
                )
            )

            items_by_type[candidate["item_type"]] += 1

    try:
        db.add_all(new_items)
        db.commit()

    except Exception as exc:
        db.rollback()

        logger.exception(
            "Knowledge extraction failed for document %s.",
            document_id,
        )

        raise HTTPException(
            500,
            "Could not save extracted knowledge records.",
        ) from exc

    return KnowledgeExtractionSummary(
        project_id=project_id,
        document_id=document_id,
        chunks_processed=len(chunks),
        candidate_items_created=len(new_items),
        duplicate_items_skipped=duplicate_count,
        items_by_type=dict(items_by_type),
        review_status="pending",
    )


# --------------------------------------------------
# GET PROJECT KNOWLEDGE
# --------------------------------------------------

@router.get(
    "/knowledge",
    response_model=list[KnowledgeItemRead],
)
def get_project_knowledge(
    project_id: int,
    item_type: str | None = None,
    review_status: str | None = None,
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(404, "Project not found.")

    query = (
        db.query(KnowledgeItem, Document, DocumentChunk)
        .join(
            Document,
            KnowledgeItem.document_id == Document.id,
        )
        .join(
            DocumentChunk,
            KnowledgeItem.chunk_id == DocumentChunk.id,
        )
        .filter(KnowledgeItem.project_id == project_id)
    )

    if item_type:
        query = query.filter(
            KnowledgeItem.item_type == item_type
        )

    if review_status:
        query = query.filter(
            KnowledgeItem.review_status == review_status
        )

    results = (
        query
        .order_by(KnowledgeItem.created_at.desc())
        .all()
    )

    response = []

    for knowledge, document, chunk in results:

        response.append({
            "id": knowledge.id,
            "project_id": knowledge.project_id,
            "document_id": knowledge.document_id,
            "chunk_id": knowledge.chunk_id,
            "item_type": knowledge.item_type,
            "title": knowledge.title,
            "description": knowledge.description,
            "source_excerpt": knowledge.source_excerpt,
            "source_locator": chunk.source_locator,
            "original_filename": document.original_filename,
            "candidate_owner_mention": (
                knowledge.candidate_owner_mention
            ),
            "assigned_to_user_id": knowledge.assigned_to_user_id,
            "work_status": knowledge.work_status,
            "review_status": knowledge.review_status,
            "reviewed_by_user_id": knowledge.reviewed_by_user_id,
            "reviewed_at": knowledge.reviewed_at,
            "review_notes": knowledge.review_notes,
            "extraction_method": knowledge.extraction_method,
            "created_at": knowledge.created_at,
        })

    return response


# --------------------------------------------------
# REVIEW KNOWLEDGE ITEM
# --------------------------------------------------

@router.patch(
    "/knowledge/{knowledge_item_id}/review",
    response_model=KnowledgeReviewResult,
)
def review_knowledge_item(
    project_id: int,
    knowledge_item_id: int,
    payload: KnowledgeReviewUpdate,
    db: Session = Depends(get_db),
):
    """
    Approve, reject or request clarification for a knowledge item.

    The supplied reviewer must be an active project owner or admin.
    Any assigned person must be an active project member.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(404, "Project not found.")

    item = (
        db.query(KnowledgeItem)
        .filter(
            KnowledgeItem.id == knowledge_item_id,
            KnowledgeItem.project_id == project_id,
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            404,
            "Knowledge item not found in this project.",
        )

    # Check the reviewer is an active project owner/admin.
    reviewer_member = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == payload.reviewed_by_user_id,
            ProjectMember.membership_status == "active",
        )
        .first()
    )

    reviewer = db.get(User, payload.reviewed_by_user_id)

    if reviewer_member is None or reviewer is None or not reviewer.is_active:
        raise HTTPException(
            403,
            "The reviewer must be an active member of this project.",
        )

    if reviewer_member.role not in ("owner", "admin"):
        raise HTTPException(
            403,
            "Only project owners and admins can review knowledge items.",
        )

    # An assignment can only be made on an approved item.
    if (
        payload.assigned_to_user_id is not None
        and payload.review_status != "approved"
    ):
        raise HTTPException(
            422,
            "A knowledge item must be approved before assigning an owner.",
        )

    # Check an explicitly provided assignee belongs to this project.
    if payload.assigned_to_user_id is not None:

        assignee_member = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == payload.assigned_to_user_id,
                ProjectMember.membership_status == "active",
                ProjectMember.role.in_(("owner", "admin", "member")),
            )
            .first()
        )

        assignee = db.get(User, payload.assigned_to_user_id)

        if assignee_member is None or assignee is None or not assignee.is_active:
            raise HTTPException(
                422,
                "The assigned person must be an active, assignable project member.",
            )

    # Update the review decision.
    item.review_status = payload.review_status
    item.reviewed_by_user_id = payload.reviewed_by_user_id
    item.reviewed_at = datetime.now(timezone.utc)

    # Only overwrite optional fields when they were supplied.
    if "review_notes" in payload.model_fields_set:
        item.review_notes = payload.review_notes

    if payload.work_status is not None:
        item.work_status = payload.work_status

    if "assigned_to_user_id" in payload.model_fields_set:
        item.assigned_to_user_id = payload.assigned_to_user_id

    # Rejecting or requesting clarification clears an existing assignment.
    elif payload.review_status != "approved":
        item.assigned_to_user_id = None

    try:
        db.commit()
        db.refresh(item)

    except Exception as exc:
        db.rollback()

        logger.exception(
            "Could not review knowledge item %s.",
            knowledge_item_id,
        )

        raise HTTPException(
            500,
            "Could not save the knowledge review.",
        ) from exc

    return KnowledgeReviewResult(
        id=item.id,
        project_id=item.project_id,
        item_type=item.item_type,
        review_status=item.review_status,
        work_status=item.work_status,
        assigned_to_user_id=item.assigned_to_user_id,
        reviewed_by_user_id=item.reviewed_by_user_id,
        reviewed_at=item.reviewed_at,
        review_notes=item.review_notes,
    )