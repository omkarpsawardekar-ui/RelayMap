from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeRelationshipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_item_id: int = Field(gt=0)
    target_item_id: int = Field(gt=0)

    relation_type: Literal[
        "depends_on",
        "blocks",
        "related_to",
        "supports",
        "informs",
    ]

    evidence_chunk_id: int = Field(gt=0)

    # Must be an exact excerpt from the selected evidence chunk.
    evidence_excerpt: str = Field(min_length=10, max_length=5000)

    created_by_user_id: int | None = None


class KnowledgeRelationshipReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: Literal["approved", "rejected"]
    reviewed_by_user_id: int

    review_notes: str | None = Field(
        default=None,
        max_length=5000,
    )


class KnowledgeRelationshipRead(BaseModel):
    id: int
    project_id: int

    source_item_id: int
    source_item_title: str

    target_item_id: int
    target_item_title: str

    relation_type: str

    evidence_chunk_id: int
    evidence_excerpt: str
    evidence_locator: str
    original_filename: str

    review_status: str
    created_at: Any
    reviewed_at: Any = None
    review_notes: str | None = None


class GraphNode(BaseModel):
    id: str
    type: str
    position: dict[str, int]
    data: dict[str, Any]


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    type: str = "smoothstep"
    animated: bool = False
    data: dict[str, Any]


class KnowledgeGraphResponse(BaseModel):
    project_id: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    summary: dict[str, int]