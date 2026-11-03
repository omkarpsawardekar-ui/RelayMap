
import logging

from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_current_user

from app.core.permissions import (
    require_project_access,
    require_project_write_access,
    require_project_management,
)

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

import re

from pydantic import BaseModel, Field

from app.services.llm_project_qa_service import (
    generate_project_answer,
    get_project_qa_model,
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
    current_user: User = Depends(get_current_user),
):
    """
    Extract knowledge candidates from a document.

    Only project owners, admins and members with write
    access can trigger knowledge extraction.
    All extracted items remain pending human review.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    # Verify that the authenticated user can modify this project.
    require_project_write_access(
        db,
        project,
        current_user.id,
    )

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.project_id == project_id,
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found in this project.",
        )

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )

    if not chunks:
        raise HTTPException(
            status_code=409,
            detail=(
                "This document has no evidence chunks. "
                "Run chunking or backfill first."
            ),
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

            # Skip records that have already been extracted.
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
            status_code=500,
            detail="Could not save extracted knowledge records.",
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
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve knowledge records belonging to a project.

    Only active project members and workspace owners/admins
    can inspect the project's knowledge records.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    # Verify read access.
    require_project_access(
        db,
        project,
        current_user.id,
    )

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
        .filter(
            KnowledgeItem.project_id == project_id
        )
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
    current_user: User = Depends(get_current_user),
):
    """
    Approve, reject or request clarification for a knowledge item.

    Only authenticated project owners/admins or workspace
    owners/admins can review knowledge records.

    Reviewer identity is derived from the authenticated JWT,
    never trusted from the request body.

    Any assigned person must be an active, assignable
    project member.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    # Verify that the authenticated user has review permission.
    require_project_management(
        db,
        project,
        current_user.id,
    )

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
            status_code=404,
            detail="Knowledge item not found in this project.",
        )

    # An assignment can only be made on an approved item.
    if (
        payload.assigned_to_user_id is not None
        and payload.review_status != "approved"
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "A knowledge item must be approved "
                "before assigning an owner."
            ),
        )

    # Verify that the assigned person belongs to this project.
    if payload.assigned_to_user_id is not None:

        assignee_member = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == payload.assigned_to_user_id,
                ProjectMember.membership_status == "active",
                ProjectMember.role.in_(
                    ("owner", "admin", "member")
                ),
            )
            .first()
        )

        assignee = db.get(
            User,
            payload.assigned_to_user_id
        )

        if (
            assignee_member is None
            or assignee is None
            or not assignee.is_active
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "The assigned person must be an active, "
                    "assignable project member."
                ),
            )

    # Update the review decision.
    item.review_status = payload.review_status

    # Never trust reviewed_by_user_id from the request body.
    item.reviewed_by_user_id = current_user.id

    item.reviewed_at = datetime.now(timezone.utc)

    # Only overwrite optional fields when supplied.
    if "review_notes" in payload.model_fields_set:
        item.review_notes = payload.review_notes

    if payload.work_status is not None:
        item.work_status = payload.work_status

    if "assigned_to_user_id" in payload.model_fields_set:
        item.assigned_to_user_id = payload.assigned_to_user_id

    # Rejected or clarification-required items lose assignment.
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
            status_code=500,
            detail="Could not save the knowledge review.",
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

# --------------------------------------------------
# ASK RELAYMAP — EVIDENCE-GROUNDED PROJECT Q&A
# --------------------------------------------------

class ProjectQuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1200)


class ProjectQuestionCitation(BaseModel):
    knowledge_item_id: int
    title: str
    document_name: str
    source_locator: str
    excerpt: str
    item_type: str


class ProjectQuestionResponse(BaseModel):
    project_id: int
    question: str
    answer: str
    sufficient_evidence: bool
    uncertainty: str
    citations: list[ProjectQuestionCitation]
    retrieval_method: str
    model: str


QA_STOP_WORDS = {
    "the", "and", "for", "from", "with", "what", "when",
    "where", "who", "why", "how", "does", "did", "was",
    "were", "are", "is", "a", "an", "to", "of", "in",
    "on", "our", "their", "this", "that", "it", "we",
    "you", "can", "could", "would", "should", "be",
    "been", "has", "have", "had", "about", "please",
    "tell", "show", "explain", "project",
}


def get_question_tokens(question: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9]+", question.lower())

    return {
        word
        for word in words
        if len(word) >= 2 and word not in QA_STOP_WORDS
    }


def score_knowledge_match(
    tokens: set[str],
    question: str,
    item,
) -> int:
    title_words = set(
        re.findall(r"[a-zA-Z0-9]+", item.title.lower())
    )

    description_words = set(
        re.findall(r"[a-zA-Z0-9]+", item.description.lower())
    )

    excerpt_words = set(
        re.findall(r"[a-zA-Z0-9]+", item.source_excerpt.lower())
    )

    score = (
        len(tokens & title_words) * 6
        + len(tokens & description_words) * 3
        + len(tokens & excerpt_words)
    )

    searchable_text = " ".join([
        item.title,
        item.description,
        item.source_excerpt,
    ]).lower()

    clean_question = question.lower().strip()

    if len(clean_question) >= 8 and clean_question in searchable_text:
        score += 5

    return score


@router.post(
    "/ask",
    response_model=ProjectQuestionResponse,
)
def ask_project_question(
    project_id: int,
    payload: ProjectQuestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    question = payload.question.strip()

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    # Only users with project read access can ask questions.
    require_project_access(
        db,
        project,
        current_user.id,
    )

    tokens = get_question_tokens(question)

    if not tokens:
        return ProjectQuestionResponse(
            project_id=project_id,
            question=question,
            answer=(
                "Please ask a more specific question so I can "
                "match it against the approved project knowledge."
            ),
            sufficient_evidence=False,
            uncertainty="The question did not contain enough searchable terms.",
            citations=[],
            retrieval_method="keyword_match_over_approved_knowledge",
            model=get_project_qa_model(),
        )

    # Retrieve approved records from this project only.
    rows = (
        db.query(
            KnowledgeItem,
            Document,
            DocumentChunk,
            User,
        )
        .join(
            Document,
            KnowledgeItem.document_id == Document.id,
        )
        .join(
            DocumentChunk,
            KnowledgeItem.chunk_id == DocumentChunk.id,
        )
        .outerjoin(
            User,
            KnowledgeItem.assigned_to_user_id == User.id,
        )
        .filter(
            KnowledgeItem.project_id == project_id,
            KnowledgeItem.review_status == "approved",
        )
        .order_by(KnowledgeItem.created_at.desc())
        .limit(2000)
        .all()
    )

    ranked_records = []

    for item, document, chunk, assigned_user in rows:
        score = score_knowledge_match(
            tokens,
            question,
            item,
        )

        if score <= 0:
            continue

        owner_name = (
            assigned_user.full_name
            if assigned_user is not None
            else None
        )

        evidence = {
            "knowledge_item_id": item.id,
            "item_type": item.item_type,
            "title": item.title,
            "description": item.description,
            "work_status": item.work_status,
            "assigned_owner": owner_name,
            "document_name": document.original_filename,
            "source_locator": chunk.source_locator,
            "excerpt": item.source_excerpt,
        }

        ranked_records.append({
            "score": score,
            "evidence": evidence,
        })

    ranked_records.sort(
        key=lambda record: record["score"],
        reverse=True,
    )

    # Keep the prompt small and focused.
    selected_records = ranked_records[:8]

    if not selected_records:
        return ProjectQuestionResponse(
            project_id=project_id,
            question=question,
            answer=(
                "I couldn't find approved project knowledge that "
                "directly supports an answer to this question. "
                "Try a more specific question or add and approve "
                "the relevant project information."
            ),
            sufficient_evidence=False,
            uncertainty=(
                "No relevant approved knowledge records matched "
                "the question. Pending and rejected records were excluded."
            ),
            citations=[],
            retrieval_method="keyword_match_over_approved_knowledge",
            model=get_project_qa_model(),
        )

    evidence_payload = [
        record["evidence"]
        for record in selected_records
    ]

    try:
        ai_result = generate_project_answer(
            question=question,
            approved_evidence=evidence_payload,
        )

    except RuntimeError as exc:
        logger.exception("RelayMap project Q&A failed.")

        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    # Validate every model-generated citation against the
    # evidence records actually supplied to the model.
    evidence_by_id = {
        item["knowledge_item_id"]: item
        for item in evidence_payload
    }

    valid_cited_ids = []

    for cited_id in ai_result.get(
        "cited_knowledge_item_ids",
        [],
    ):
        if (
            isinstance(cited_id, int)
            and cited_id in evidence_by_id
            and cited_id not in valid_cited_ids
        ):
            valid_cited_ids.append(cited_id)

    sufficient_evidence = bool(
        ai_result.get("sufficient_evidence", False)
    )

    answer = str(ai_result.get("answer", "")).strip()

    uncertainty = str(
        ai_result.get("uncertainty", "")
    ).strip()

    # A supported answer must cite at least one retrieved record.
    if sufficient_evidence and not valid_cited_ids:
        sufficient_evidence = False
        answer = (
            "I couldn't verify a reliable answer from the approved "
            "records retrieved for this question."
        )
        uncertainty = (
            "The AI response did not provide a valid citation "
            "to the retrieved approved evidence."
        )

    citations = [
        ProjectQuestionCitation(
            knowledge_item_id=evidence_by_id[item_id][
                "knowledge_item_id"
            ],
            title=evidence_by_id[item_id]["title"],
            document_name=evidence_by_id[item_id]["document_name"],
            source_locator=evidence_by_id[item_id]["source_locator"],
            excerpt=evidence_by_id[item_id]["excerpt"],
            item_type=evidence_by_id[item_id]["item_type"],
        )
        for item_id in valid_cited_ids
    ]

    return ProjectQuestionResponse(
        project_id=project_id,
        question=question,
        answer=answer,
        sufficient_evidence=sufficient_evidence,
        uncertainty=uncertainty,
        citations=citations,
        retrieval_method="keyword_match_over_approved_knowledge",
        model=get_project_qa_model(),
    )