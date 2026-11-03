
import hashlib
import logging

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.db.session import get_db

from app.core.dependencies import get_current_user
from app.core.permissions import (
    require_project_access,
    require_project_management,
    require_project_write_access,
)

from app.models import (
    Project,
    ProjectMember,
    User,
    Document,
    DocumentChunk,
    KnowledgeItem,
    KnowledgeRelationship,
)

from app.schemas.knowledge_relationship import (
    KnowledgeRelationshipCreate,
    KnowledgeRelationshipReview,
    KnowledgeRelationshipRead,
    KnowledgeGraphResponse,
    GraphNode,
    GraphEdge,
)

from app.services.llm_relationship_suggestion_service import (
    generate_relationship_candidates,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}",
    tags=["Knowledge Map"],
)


# --------------------------------------------------
# CREATE A PENDING EVIDENCE-BACKED RELATIONSHIP
# --------------------------------------------------

@router.post(
    "/relationships",
    response_model=KnowledgeRelationshipRead,
    status_code=201,
)
def create_relationship(
    project_id: int,
    payload: KnowledgeRelationshipCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a relationship candidate.

    Its source and target must belong to this project.
    The evidence excerpt must exist in the selected evidence chunk.
    New relationships always require human review.

    The creator is always the authenticated user.
    Client-supplied creator IDs are never trusted.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(404, "Project not found.")

    # Only users with project write access can create relationships.
    require_project_write_access(
        db,
        project,
        current_user.id,
    )

    if payload.source_item_id == payload.target_item_id:
        raise HTTPException(
            422,
            "A knowledge item cannot be related to itself.",
        )

    # Check both knowledge records belong to this project.
    knowledge_items = (
        db.query(KnowledgeItem)
        .filter(
            KnowledgeItem.project_id == project_id,
            KnowledgeItem.id.in_(
                [
                    payload.source_item_id,
                    payload.target_item_id,
                ]
            ),
        )
        .all()
    )

    item_lookup = {
        item.id: item for item in knowledge_items
    }

    source_item = item_lookup.get(payload.source_item_id)
    target_item = item_lookup.get(payload.target_item_id)

    if source_item is None or target_item is None:
        raise HTTPException(
            404,
            "Both knowledge items must exist in this project.",
        )

    # Confirm the evidence chunk belongs to a document in this project.
    evidence = (
        db.query(DocumentChunk, Document)
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .filter(
            DocumentChunk.id == payload.evidence_chunk_id,
            Document.project_id == project_id,
        )
        .first()
    )

    if evidence is None:
        raise HTTPException(
            404,
            "Evidence chunk not found in this project.",
        )

    evidence_chunk, evidence_document = evidence

    excerpt = payload.evidence_excerpt.strip()

    # Do not accept unsupported or invented evidence.
    if excerpt not in evidence_chunk.chunk_text:
        raise HTTPException(
            422,
            "The evidence excerpt must exactly match text in the selected chunk.",
        )

    evidence_hash = hashlib.sha256(
        (
            f"{payload.source_item_id}|"
            f"{payload.target_item_id}|"
            f"{payload.relation_type}|"
            f"{excerpt}"
        ).encode("utf-8")
    ).hexdigest()

    relationship = KnowledgeRelationship(
        project_id=project_id,
        source_item_id=payload.source_item_id,
        target_item_id=payload.target_item_id,
        relation_type=payload.relation_type,
        evidence_chunk_id=evidence_chunk.id,
        evidence_excerpt=excerpt,
        evidence_hash=evidence_hash,
        review_status="pending",

        # Never trust payload.created_by_user_id.
        created_by_user_id=current_user.id,
    )

    db.add(relationship)

    try:
        db.commit()
        db.refresh(relationship)

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            409,
            "This relationship with the same evidence already exists.",
        ) from exc

    except Exception as exc:
        db.rollback()

        logger.exception("Relationship creation failed.")

        raise HTTPException(
            500,
            "Could not save the relationship.",
        ) from exc

    return KnowledgeRelationshipRead(
        id=relationship.id,
        project_id=project_id,
        source_item_id=source_item.id,
        source_item_title=source_item.title,
        target_item_id=target_item.id,
        target_item_title=target_item.title,
        relation_type=relationship.relation_type,
        evidence_chunk_id=evidence_chunk.id,
        evidence_excerpt=relationship.evidence_excerpt,
        evidence_locator=evidence_chunk.source_locator,
        original_filename=evidence_document.original_filename,
        review_status=relationship.review_status,
        created_at=relationship.created_at,
        reviewed_at=relationship.reviewed_at,
        review_notes=relationship.review_notes,
    )


# --------------------------------------------------
# LIST PROJECT RELATIONSHIPS
# --------------------------------------------------

@router.get(
    "/relationships",
    response_model=list[KnowledgeRelationshipRead],
)
def get_relationships(
    project_id: int,
    review_status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return relationships belonging to a project.

    The authenticated user must have project read access.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(404, "Project not found.")

    # Read access is sufficient to view relationships.
    require_project_access(
        db,
        project,
        current_user.id,
    )

    SourceItem = aliased(KnowledgeItem)
    TargetItem = aliased(KnowledgeItem)

    query = (
        db.query(
            KnowledgeRelationship,
            SourceItem,
            TargetItem,
            DocumentChunk,
            Document,
        )
        .join(
            SourceItem,
            SourceItem.id == KnowledgeRelationship.source_item_id,
        )
        .join(
            TargetItem,
            TargetItem.id == KnowledgeRelationship.target_item_id,
        )
        .join(
            DocumentChunk,
            DocumentChunk.id == KnowledgeRelationship.evidence_chunk_id,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .filter(
            KnowledgeRelationship.project_id == project_id
        )
    )

    if review_status:
        if review_status not in (
            "pending",
            "approved",
            "rejected",
        ):
            raise HTTPException(
                422,
                "Invalid relationship review status.",
            )

        query = query.filter(
            KnowledgeRelationship.review_status == review_status
        )

    results = query.order_by(
        KnowledgeRelationship.created_at.desc()
    ).all()

    return [
        KnowledgeRelationshipRead(
            id=relationship.id,
            project_id=relationship.project_id,
            source_item_id=source_item.id,
            source_item_title=source_item.title,
            target_item_id=target_item.id,
            target_item_title=target_item.title,
            relation_type=relationship.relation_type,
            evidence_chunk_id=evidence_chunk.id,
            evidence_excerpt=relationship.evidence_excerpt,
            evidence_locator=evidence_chunk.source_locator,
            original_filename=document.original_filename,
            review_status=relationship.review_status,
            created_at=relationship.created_at,
            reviewed_at=relationship.reviewed_at,
            review_notes=relationship.review_notes,
        )
        for (
            relationship,
            source_item,
            target_item,
            evidence_chunk,
            document,
        ) in results
    ]


# --------------------------------------------------
# APPROVE OR REJECT A RELATIONSHIP
# --------------------------------------------------

@router.patch(
    "/relationships/{relationship_id}/review",
)
def review_relationship(
    project_id: int,
    relationship_id: int,
    payload: KnowledgeRelationshipReview,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Approve or reject a pending relationship.

    Only project owners/admins or workspace owners/admins
    can review relationships.

    The reviewer is always the authenticated user.
    Client-supplied reviewer IDs are never trusted.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(404, "Project not found.")

    # Review requires management permission.
    require_project_management(
        db,
        project,
        current_user.id,
    )

    relationship = (
        db.query(KnowledgeRelationship)
        .filter(
            KnowledgeRelationship.id == relationship_id,
            KnowledgeRelationship.project_id == project_id,
        )
        .first()
    )

    if relationship is None:
        raise HTTPException(
            404,
            "Relationship not found in this project.",
        )

    # A relationship is only approved if both endpoints are approved.
    if payload.review_status == "approved":

        endpoint_items = (
            db.query(KnowledgeItem)
            .filter(
                KnowledgeItem.id.in_(
                    [
                        relationship.source_item_id,
                        relationship.target_item_id,
                    ]
                ),
                KnowledgeItem.project_id == project_id,
            )
            .all()
        )

        if (
            len(endpoint_items) != 2
            or any(
                item.review_status != "approved"
                for item in endpoint_items
            )
        ):
            raise HTTPException(
                409,
                "Both linked knowledge items must be approved before approving this relationship.",
            )

    relationship.review_status = payload.review_status

    # Never trust payload.reviewed_by_user_id.
    relationship.reviewed_by_user_id = current_user.id

    relationship.reviewed_at = datetime.now(timezone.utc)
    relationship.review_notes = payload.review_notes

    try:
        db.commit()
        db.refresh(relationship)

    except Exception as exc:
        db.rollback()

        logger.exception("Relationship review failed.")

        raise HTTPException(
            500,
            "Could not save relationship review.",
        ) from exc

    return {
        "id": relationship.id,
        "project_id": relationship.project_id,
        "review_status": relationship.review_status,
        "reviewed_by_user_id": relationship.reviewed_by_user_id,
        "reviewed_at": relationship.reviewed_at,
        "review_notes": relationship.review_notes,
    }


# --------------------------------------------------
# AUTOMATIC RELATIONSHIP SUGGESTIONS
# --------------------------------------------------

@router.post(
    "/relationships/suggest",
)
def suggest_project_relationships(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Scan project evidence for explicit relationship language.

    Only approved knowledge items can be relationship endpoints.
    All generated relationships remain pending human review.

    Generating suggestions writes to the database, so the user
    must have project write access.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    require_project_write_access(
        db,
        project,
        current_user.id,
    )

    approved_items = (
        db.query(KnowledgeItem)
        .filter(
            KnowledgeItem.project_id == project_id,
            KnowledgeItem.review_status == "approved",
        )
        .order_by(KnowledgeItem.id.asc())
        .all()
    )

    if len(approved_items) < 2:
        return {
            "project_id": project_id,
            "approved_knowledge_items": len(approved_items),
            "chunks_scanned": 0,
            "candidates_detected": 0,
            "suggestions_created": 0,
            "duplicates_skipped": 0,
            "suggestions": [],
            "message": (
                "At least two approved knowledge items are required."
            ),
        }

    chunks = (
        db.query(DocumentChunk)
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .filter(
            Document.project_id == project_id,
        )
        .order_by(
            DocumentChunk.document_id.asc(),
            DocumentChunk.chunk_index.asc(),
        )
        .all()
    )

   
    chunks_to_scan = chunks[:25]

    try:
        candidates = generate_relationship_candidates(
            approved_items=approved_items,
            chunks=chunks_to_scan,
        )

    except RuntimeError as exc:
        logger.exception(
            "AI relationship generation failed for project %s.",
            project_id,
        )

        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    


    existing_rows = (
        db.query(
            KnowledgeRelationship.source_item_id,
            KnowledgeRelationship.target_item_id,
            KnowledgeRelationship.relation_type,
            KnowledgeRelationship.evidence_hash,
        )
        .filter(
            KnowledgeRelationship.project_id == project_id,
        )
        .all()
    )

    existing_keys = set(existing_rows)

    item_lookup = {
        item.id: item for item in approved_items
    }

    new_relationships = []
    duplicates_skipped = 0

    for candidate in candidates:

        unique_key = (
            candidate["source_item_id"],
            candidate["target_item_id"],
            candidate["relation_type"],
            candidate["evidence_hash"],
        )

        if unique_key in existing_keys:
            duplicates_skipped += 1
            continue

        # Automatically generated suggestions have no human creator.
        # They remain pending until an authorized person reviews them.
        relationship = KnowledgeRelationship(
            project_id=project_id,
            source_item_id=candidate["source_item_id"],
            target_item_id=candidate["target_item_id"],
            relation_type=candidate["relation_type"],
            evidence_chunk_id=candidate["evidence_chunk_id"],
            evidence_excerpt=candidate["evidence_excerpt"],
            evidence_hash=candidate["evidence_hash"],
            review_status="pending",
            created_by_user_id=None,
        )

        db.add(relationship)
        new_relationships.append((relationship, candidate))

        existing_keys.add(unique_key)

    try:
        db.flush()

        response_suggestions = []

        for relationship, candidate in new_relationships:

            source = item_lookup[candidate["source_item_id"]]
            target = item_lookup[candidate["target_item_id"]]

            response_suggestions.append({
                "relationship_id": relationship.id,
                "source_item_id": source.id,
                "source_item_title": source.title,
                "target_item_id": target.id,
                "target_item_title": target.title,
                "relation_type": relationship.relation_type,
                "evidence_chunk_id": relationship.evidence_chunk_id,
                "review_status": relationship.review_status,
            })

        db.commit()

    except Exception as exc:
        db.rollback()

        logger.exception(
            "Automatic relationship suggestion failed for project %s.",
            project_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Could not save relationship suggestions.",
        ) from exc

    return {
        "project_id": project_id,
        "approved_knowledge_items": len(approved_items),
        "chunks_scanned": len(chunks),
        "chunks_available": len(chunks),
        "candidates_detected": len(candidates),
        "suggestions_created": len(new_relationships),
        "duplicates_skipped": duplicates_skipped,
        "suggestions": response_suggestions,
        "message": (
            "Suggestions created. Human review is required before "
            "they appear in the Knowledge Map."
            if new_relationships
            else
            "No new unambiguous relationship suggestions were created."
        ),
    }


# --------------------------------------------------
# BUILD THE PROJECT KNOWLEDGE GRAPH
# --------------------------------------------------

@router.get(
    "/knowledge-graph",
    response_model=KnowledgeGraphResponse,
)
def get_knowledge_graph(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return graph-ready nodes and edges.

    Only approved knowledge records and approved explicit
    relationships are included.

    Verified assignments create person-to-task connections.

    The authenticated user must have project read access.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(404, "Project not found.")

    require_project_access(
        db,
        project,
        current_user.id,
    )

    nodes = []
    edges = []

    # --------------------------------------------------
    # PEOPLE NODES
    # --------------------------------------------------

    member_rows = (
        db.query(ProjectMember, User)
        .join(
            User,
            User.id == ProjectMember.user_id,
        )
        .filter(
            ProjectMember.project_id == project_id
        )
        .order_by(ProjectMember.id.asc())
        .all()
    )

    member_ids = set()

    for index, (member, user) in enumerate(member_rows):

        member_ids.add(member.user_id)

        nodes.append(
            GraphNode(
                id=f"user-{user.id}",
                type="default",
                position={
                    "x": 70,
                    "y": 80 + index * 125,
                },
                data={
                    "label": user.full_name,
                    "kind": "person",
                    "user_id": user.id,
                    "role": member.role,
                    "membership_status": member.membership_status,
                    "responsibility": member.responsibility,
                },
            )
        )

    # --------------------------------------------------
    # APPROVED KNOWLEDGE NODES
    # --------------------------------------------------

    knowledge_rows = (
        db.query(KnowledgeItem, Document, DocumentChunk)
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
            KnowledgeItem.review_status == "approved",
        )
        .order_by(KnowledgeItem.id.asc())
        .all()
    )

    knowledge_ids = set()
    item_type_counts = {}

    for index, (item, document, chunk) in enumerate(knowledge_rows):

        knowledge_ids.add(item.id)

        item_type_counts[item.item_type] = (
            item_type_counts.get(item.item_type, 0) + 1
        )

        nodes.append(
            GraphNode(
                id=f"knowledge-{item.id}",
                type="default",
                position={
                    "x": 460,
                    "y": 80 + index * 115,
                },
                data={
                    "label": item.title,
                    "kind": "knowledge",
                    "item_type": item.item_type,
                    "knowledge_item_id": item.id,
                    "work_status": item.work_status,
                    "assigned_to_user_id": item.assigned_to_user_id,
                    "source_filename": document.original_filename,
                    "source_locator": chunk.source_locator,
                    "source_excerpt": item.source_excerpt,
                },
            )
        )

        # Add an assignment edge only for a verified project member.
        if (
            item.assigned_to_user_id is not None
            and item.assigned_to_user_id in member_ids
        ):
            edges.append(
                GraphEdge(
                    id=f"assignment-{item.id}-{item.assigned_to_user_id}",
                    source=f"knowledge-{item.id}",
                    target=f"user-{item.assigned_to_user_id}",
                    label="assigned to",
                    data={
                        "relation_type": "assigned_to",
                        "work_status": item.work_status,
                    },
                )
            )

    # --------------------------------------------------
    # APPROVED KNOWLEDGE RELATIONSHIP EDGES
    # --------------------------------------------------

    relationship_rows = (
        db.query(
            KnowledgeRelationship,
            DocumentChunk,
            Document,
        )
        .join(
            DocumentChunk,
            DocumentChunk.id == KnowledgeRelationship.evidence_chunk_id,
        )
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
        .filter(
            KnowledgeRelationship.project_id == project_id,
            KnowledgeRelationship.review_status == "approved",
        )
        .order_by(KnowledgeRelationship.id.asc())
        .all()
    )

    approved_relationship_count = 0

    for relationship, chunk, document in relationship_rows:

        # Do not show connections to hidden or unapproved nodes.
        if (
            relationship.source_item_id not in knowledge_ids
            or relationship.target_item_id not in knowledge_ids
        ):
            continue

        edges.append(
            GraphEdge(
                id=f"relationship-{relationship.id}",
                source=f"knowledge-{relationship.source_item_id}",
                target=f"knowledge-{relationship.target_item_id}",
                label=relationship.relation_type.replace("_", " "),
                data={
                    "relation_type": relationship.relation_type,
                    "relationship_id": relationship.id,
                    "evidence_excerpt": relationship.evidence_excerpt,
                    "source_filename": document.original_filename,
                    "source_locator": chunk.source_locator,
                },
            )
        )

        approved_relationship_count += 1

    assignment_count = sum(
        1 for edge in edges
        if edge.data.get("relation_type") == "assigned_to"
    )

    summary = {
        "people": len(member_rows),
        "knowledge_items": len(knowledge_rows),
        "relationships": approved_relationship_count,
        "assignments": assignment_count,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }

    return KnowledgeGraphResponse(
        project_id=project_id,
        nodes=nodes,
        edges=edges,
        summary=summary,
    )