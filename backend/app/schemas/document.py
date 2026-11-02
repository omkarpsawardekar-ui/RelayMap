from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    original_filename: str
    file_type: str
    mime_type: str | None
    size_bytes: int
    sha256: str
    extraction_status: str
    uploaded_at: datetime