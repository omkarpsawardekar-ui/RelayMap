
from datetime import datetime, timezone
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import (
    require_project_access,
    require_project_write_access,
)

from app.models.user import User
from app.models.project import Project
from app.models.github_item import GitHubItem
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_item import KnowledgeItem

from app.services.github_services import (
    fetch_github_repository,
    GitHubAPIError,
)

from app.services.chunking_services import split_text

from app.services.knowledge_extraction_service import (
    extract_candidates_from_chunk,
)


router = APIRouter(
    prefix="/api/projects/{project_id}/github",
    tags=["GitHub Integration"],
)


# =========================================================
# REQUEST SCHEMA
# =========================================================

class GitHubRepositoryRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)


# =========================================================
# HELPERS
# =========================================================

def parse_github_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed

    except (ValueError, TypeError, AttributeError):
        return None


def build_github_item_values(
    item: dict,
    item_type: str,
    repository: dict,
):
    author = item.get("author") or {}

    return {
        "repository_full_name": repository["full_name"],
        "repository_url": repository.get("html_url"),

        "github_id": item["github_id"],
        "item_number": item["number"],
        "item_type": item_type,

        "title": item["title"],
        "body": item.get("body"),
        "state": item.get("state"),
        "state_reason": item.get("state_reason"),

        "draft": item.get("draft", False),
        "merged": item.get("merged", False),

        "url": item.get("url"),

        "author_login": author.get("login"),

        "assignees": item.get("assignees") or [],
        "labels": item.get("labels") or [],

        "base_branch": item.get("base_branch"),
        "head_branch": item.get("head_branch"),

        "github_created_at": parse_github_datetime(
            item.get("created_at")
        ),

        "github_updated_at": parse_github_datetime(
            item.get("updated_at")
        ),

        "github_closed_at": parse_github_datetime(
            item.get("closed_at")
        ),

        "github_merged_at": parse_github_datetime(
            item.get("merged_at")
        ),

        "synced_at": datetime.now(timezone.utc),
    }


def get_project_or_404(db: Session, project_id: int):
    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="RelayMap project not found.",
        )

    return project


# =========================================================
# PREVIEW GITHUB REPOSITORY
# =========================================================

@router.post("/preview")
def preview_github_repository(
    project_id: int,
    request: GitHubRepositoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)

    # Preview does not modify the database.
    # Project read access is sufficient.
    require_project_access(
        db,
        project,
        current_user.id,
    )

    try:
        result = fetch_github_repository(
            request.owner,
            request.repo,
        )

        result["project_id"] = project_id
        result["project_name"] = project.name

        return result

    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc


# =========================================================
# SYNC GITHUB REPOSITORY INTO POSTGRESQL
# =========================================================

@router.post("/sync")
def sync_github_repository(
    project_id: int,
    request: GitHubRepositoryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)

    # Synchronization writes GitHub records into the project.
    require_project_write_access(
        db,
        project,
        current_user.id,
    )

    # Step 1: Fetch the repository and its records from GitHub.
    try:
        result = fetch_github_repository(
            request.owner,
            request.repo,
        )

    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc

    repository = result["repository"]

    repository_name = repository["full_name"]

    all_records = []

    for issue in result["issues"]:
        all_records.append(("issue", issue))

    for pull_request in result["pull_requests"]:
        all_records.append(("pull_request", pull_request))

    # Step 2: Load records already stored for this project/repository.
    existing_records = (
        db.query(GitHubItem)
        .filter(
            GitHubItem.project_id == project_id,
            GitHubItem.repository_full_name == repository_name,
        )
        .all()
    )

    existing_by_github_id = {
        record.github_id: record
        for record in existing_records
    }

    created_count = 0
    updated_count = 0
    skipped_count = 0

    # Step 3: Insert new records or update existing ones.
    try:
        for item_type, item in all_records:

            github_id = item.get("github_id")
            item_number = item.get("number")
            title = item.get("title")

            if (
                github_id is None
                or item_number is None
                or not title
            ):
                skipped_count += 1
                continue

            values = build_github_item_values(
                item=item,
                item_type=item_type,
                repository=repository,
            )

            existing = existing_by_github_id.get(github_id)

            if existing:
                # Update the existing record instead of duplicating it.
                for field, value in values.items():
                    setattr(existing, field, value)

                updated_count += 1

            else:
                new_record = GitHubItem(
                    project_id=project_id,
                    **values,
                )

                db.add(new_record)

                # Keep this in memory so duplicates in the same
                # response cannot create duplicate ORM objects.
                existing_by_github_id[github_id] = new_record

                created_count += 1

        # Step 4: Commit the entire sync transaction.
        db.commit()

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="GitHub records could not be saved to PostgreSQL.",
        ) from exc

    # Step 5: Return the sync summary.
    total_stored = (
        db.query(GitHubItem)
        .filter(
            GitHubItem.project_id == project_id,
            GitHubItem.repository_full_name == repository_name,
        )
        .count()
    )

    return {
        "message": "GitHub synchronization completed.",
        "project_id": project_id,
        "project_name": project.name,
        "repository": repository_name,
        "repository_url": repository.get("html_url"),

        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,

        "fetched_issues": result["counts"]["issues"],
        "fetched_pull_requests": result["counts"]["pull_requests"],

        "total_stored_records": total_stored,

        "synced_at": datetime.now(timezone.utc).isoformat(),

        "pagination_note": result.get("pagination_note"),
    }


# =========================================================
# VIEW IMPORTED GITHUB RECORDS
# =========================================================

@router.get("/items")
def get_github_items(
    project_id: int,
    item_type: str | None = Query(
        default=None,
        pattern="^(issue|pull_request)$",
    ),
    state: str | None = Query(
        default=None,
        pattern="^(open|closed)$",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)

    # Users must have read access to see imported GitHub records.
    require_project_access(
        db,
        project,
        current_user.id,
    )

    query = (
        db.query(GitHubItem)
        .filter(GitHubItem.project_id == project_id)
    )

    if item_type:
        query = query.filter(
            GitHubItem.item_type == item_type
        )

    if state:
        query = query.filter(
            GitHubItem.state == state
        )

    records = (
        query
        .order_by(GitHubItem.github_updated_at.desc())
        .all()
    )

    return {
        "project_id": project_id,
        "total": len(records),
        "items": [
            {
                "id": item.id,
                "github_id": item.github_id,
                "number": item.item_number,
                "type": item.item_type,
                "title": item.title,
                "body": item.body,
                "state": item.state,
                "url": item.url,
                "author": item.author_login,
                "assignees": item.assignees,
                "labels": item.labels,
                "draft": item.draft,
                "merged": item.merged,
                "base_branch": item.base_branch,
                "head_branch": item.head_branch,
                "github_created_at": item.github_created_at,
                "github_updated_at": item.github_updated_at,
                "synced_at": item.synced_at,
            }
            for item in records
        ],
    }


# =========================================================
# IMPORT GITHUB RECORDS INTO THE KNOWLEDGE PIPELINE
# =========================================================

@router.post("/extract")
def extract_github_knowledge(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)

    # Extraction creates project documents, chunks and knowledge items.
    require_project_write_access(
        db,
        project,
        current_user.id,
    )

    # Step 1: Get all previously imported GitHub records.
    github_records = (
        db.query(GitHubItem)
        .filter(GitHubItem.project_id == project_id)
        .order_by(GitHubItem.item_number.asc())
        .all()
    )

    if not github_records:
        return {
            "message": "No GitHub records found. Sync a repository first.",
            "project_id": project_id,
            "records_processed": 0,
            "documents_created": 0,
            "chunks_created": 0,
            "candidates_created": 0,
            "duplicates_skipped": 0,
        }

    documents_created = 0
    chunks_created = 0
    candidates_created = 0
    duplicates_skipped = 0
    records_processed = 0

    try:
        for record in github_records:

            # Step 2: Prepare source content from the original
            # GitHub issue or pull request title and body.
            source_text = "\n\n".join(
                part.strip()
                for part in [
                    record.title or "",
                    record.body or "",
                ]
                if part and part.strip()
            )

            if not source_text:
                continue

            content_bytes = source_text.encode("utf-8")

            content_hash = hashlib.sha256(
                content_bytes
            ).hexdigest()

            item_type = (
                "issue"
                if record.item_type == "issue"
                else "pull_request"
            )

            # The source filename is deterministic for this
            # exact GitHub record and content snapshot.
            stored_filename = (
                f"github-p{project_id}-"
                f"{record.github_id}-"
                f"{content_hash[:12]}.md"
            )

            # Step 3: Reuse an existing source snapshot
            # if this exact content has already been imported.
            document = (
                db.query(Document)
                .filter(
                    Document.project_id == project_id,
                    Document.stored_filename == stored_filename,
                )
                .first()
            )

            if document is None:

                virtual_source_path = (
                    f"github://{record.repository_full_name}/"
                    f"{item_type}s/{record.item_number}"
                )

                document = Document(
                    project_id=project_id,

                    original_filename=(
                        f"GitHub {item_type.replace('_', ' ').title()} "
                        f"#{record.item_number} - {record.title}"
                    )[:255],

                    stored_filename=stored_filename,
                    file_type="md",
                    mime_type="text/markdown",

                    # A virtual GitHub URI, not a local filesystem path.
                    file_path=virtual_source_path,

                    size_bytes=len(content_bytes),
                    sha256=content_hash,

                    extraction_status="processed",
                    extracted_text=source_text,
                )

                db.add(document)
                db.flush()

                documents_created += 1

                # Step 4: Build evidence chunks from the issue
                # or pull request content.
                text_parts = split_text(source_text)

                for part_number, text_part in enumerate(
                    text_parts,
                    start=1,
                ):
                    chunk_hash = hashlib.sha256(
                        text_part.encode("utf-8")
                    ).hexdigest()

                    locator = (
                        f"github:{item_type}/{record.item_number}"
                    )

                    if len(text_parts) > 1:
                        locator += (
                            f",part:{part_number}/{len(text_parts)}"
                        )

                    chunk = DocumentChunk(
                        document_id=document.id,
                        chunk_index=part_number,
                        source_locator=locator[:120],
                        chunk_text=text_part,
                        content_sha256=chunk_hash,
                    )

                    db.add(chunk)
                    db.flush()

                    chunks_created += 1

            # Step 5: Retrieve all chunks associated with this
            # exact source snapshot.
            source_chunks = (
                db.query(DocumentChunk)
                .filter(
                    DocumentChunk.document_id == document.id
                )
                .order_by(DocumentChunk.chunk_index.asc())
                .all()
            )

            # Step 6: Run the existing deterministic extractor.
            for chunk in source_chunks:

                candidates = extract_candidates_from_chunk(
                    chunk.chunk_text
                )

                for candidate in candidates:

                    # Check for an identical candidate first.
                    existing_candidate = (
                        db.query(KnowledgeItem)
                        .filter(
                            KnowledgeItem.project_id == project_id,
                            KnowledgeItem.chunk_id == chunk.id,
                            KnowledgeItem.item_type
                            == candidate["item_type"],
                            KnowledgeItem.evidence_hash
                            == candidate["evidence_hash"],
                        )
                        .first()
                    )

                    if existing_candidate:
                        duplicates_skipped += 1
                        continue

                    # All GitHub-derived candidates require
                    # the same human review as document candidates.
                    knowledge_item = KnowledgeItem(
                        project_id=project_id,
                        document_id=document.id,
                        chunk_id=chunk.id,

                        item_type=candidate["item_type"],
                        title=candidate["title"],
                        description=candidate["description"],

                        source_excerpt=candidate["source_excerpt"],
                        evidence_hash=candidate["evidence_hash"],

                        candidate_owner_mention=(
                            candidate["candidate_owner_mention"]
                        ),

                        # GitHub state and assignees are source data,
                        # not verified RelayMap ownership.
                        work_status="unknown",
                        review_status="pending",

                        extraction_method="github_rule_based",
                    )

                    db.add(knowledge_item)
                    candidates_created += 1

            records_processed += 1

        # Step 7: Save all source documents, chunks and candidates.
        db.commit()

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                "GitHub knowledge extraction failed. "
                "The database changes were rolled back."
            ),
        ) from exc

    return {
        "message": (
            "GitHub records processed into evidence-backed "
            "knowledge candidates."
        ),

        "project_id": project_id,
        "project_name": project.name,

        "records_processed": records_processed,

        "documents_created": documents_created,
        "chunks_created": chunks_created,

        "candidates_created": candidates_created,
        "duplicates_skipped": duplicates_skipped,

        "review_status": "pending",

        "important_note": (
            "GitHub usernames, assignees and task states "
            "must be verified by a human before they are "
            "treated as RelayMap ownership or work status."
        ),
    }