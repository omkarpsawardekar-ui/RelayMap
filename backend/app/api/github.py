from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.project import Project
from app.models.github_item import GitHubItem

from app.services.github_services import (
    fetch_github_repository,
    GitHubAPIError,
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

    except (ValueError, TypeError):
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
    project = (
        db.query(Project)
        .filter(Project.id == project_id)
        .first()
    )

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
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)

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
    db: Session = Depends(get_db),
):
    project = get_project_or_404(db, project_id)

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
    db: Session = Depends(get_db),
):
    get_project_or_404(db, project_id)

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