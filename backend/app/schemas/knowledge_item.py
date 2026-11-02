from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    document_id: int
    chunk_id: int

    item_type: str
    title: str
    description: str
    source_excerpt: str
    source_locator: str
    original_filename: str

    candidate_owner_mention: str | None
    assigned_to_user_id: int | None

    work_status: str
    review_status: str

    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    review_notes: str | None

    extraction_method: str
    created_at: datetime


class KnowledgeExtractionSummary(BaseModel):
    project_id: int
    document_id: int

    chunks_processed: int
    candidate_items_created: int
    duplicate_items_skipped: int

    items_by_type: dict[str, int]

    review_status: str