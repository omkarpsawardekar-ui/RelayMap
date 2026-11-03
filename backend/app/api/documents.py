
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.core.permissions import (
    require_project_access,
    require_project_write_access,
)

from app.models import (
    Document,
    DocumentChunk,
    Project,
    User,
)

from app.schemas.document import DocumentRead
from app.schemas.document_chunk import DocumentChunkRead

from app.services.document_service import (
    store_and_extract_upload,
    delete_stored_file,
)

from app.services.chunking_services import build_document_chunks


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/projects/{project_id}/documents",
    tags=["Documents"],
)


# --------------------------------------------------
# UPLOAD DOCUMENT
# --------------------------------------------------

@router.post(
    "",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a document, extract text and create evidence chunks.

    Only project owners, admins and members with write access
    can upload documents.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    # Verify that the authenticated user can upload to this project.
    require_project_write_access(
        db,
        project,
        current_user.id,
    )

    upload_data = await store_and_extract_upload(
        file,
        project_id,
    )

    stored_path = upload_data["file_path"]

    try:
        # Build source-linked chunks from the original file.
        chunks = build_document_chunks(
            file_path=stored_path,
            file_type=upload_data["file_type"],
            fallback_text=upload_data.get("extracted_text"),
        )

        # Register the document first to obtain its database ID.
        document = Document(
            project_id=project_id,
            original_filename=upload_data["original_filename"],
            stored_filename=upload_data["stored_filename"],
            file_type=upload_data["file_type"],
            mime_type=upload_data["mime_type"],
            file_path=stored_path,
            size_bytes=upload_data["size_bytes"],
            sha256=upload_data["sha256"],
            extraction_status="processed",
            extracted_text=upload_data["extracted_text"],
        )

        db.add(document)
        db.flush()

        # Link every evidence chunk to the new document.
        chunk_records = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=chunk["chunk_index"],
                source_locator=chunk["source_locator"],
                chunk_text=chunk["chunk_text"],
                content_sha256=chunk["content_sha256"],
            )
            for chunk in chunks
        ]

        db.add_all(chunk_records)

        # Save the document and all chunks together.
        db.commit()
        db.refresh(document)

        return document

    except HTTPException:
        db.rollback()
        delete_stored_file(stored_path)
        raise

    except (ValueError, FileNotFoundError) as exc:
        db.rollback()
        delete_stored_file(stored_path)

        raise HTTPException(
            status_code=422,
            detail=f"Could not create evidence chunks: {exc}",
        ) from exc

    except Exception as exc:
        db.rollback()
        delete_stored_file(stored_path)

        logger.exception(
            "Failed to save document and evidence chunks."
        )

        raise HTTPException(
            status_code=500,
            detail="Could not save the document and its evidence chunks.",
        ) from exc


# --------------------------------------------------
# GET PROJECT DOCUMENTS
# --------------------------------------------------

@router.get(
    "",
    response_model=list[DocumentRead],
)
def get_project_documents(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List documents belonging to a project.

    Only active project members and workspace owners/admins
    can view these documents.
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

    return (
        db.query(Document)
        .filter(Document.project_id == project_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )


# --------------------------------------------------
# GET DOCUMENT EVIDENCE CHUNKS
# --------------------------------------------------

@router.get(
    "/{document_id}/chunks",
    response_model=list[DocumentChunkRead],
)
def get_document_chunks(
    project_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Inspect evidence chunks belonging to a document.

    The user must have read access to the parent project,
    and the document must belong to that project.
    """

    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found.",
        )

    # Verify read access before returning evidence.
    require_project_access(
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

    return (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )