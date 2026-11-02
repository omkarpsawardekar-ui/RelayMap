
import csv
import hashlib
import logging
import zipfile

from pathlib import Path
from uuid import uuid4

import fitz
from docx import Document as WordDocument
from fastapi import HTTPException, UploadFile


logger = logging.getLogger(__name__)

# Files are stored inside backend/storage/
STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage"

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".csv"}

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB
CHUNK_SIZE = 1024 * 1024  # 1 MB


def extract_document_text(file_path: Path, extension: str) -> str:
    """Extract readable text from supported document formats."""

    if extension == ".pdf":
        text_parts = []

        with fitz.open(str(file_path)) as pdf:
            if pdf.is_encrypted and not pdf.authenticate(""):
                raise ValueError("Password-protected PDFs are not supported.")

            for page in pdf:
                text_parts.append(page.get_text("text"))

        return "\n".join(text_parts)

    if extension == ".docx":
        document = WordDocument(str(file_path))

        parts = [paragraph.text for paragraph in document.paragraphs]

        # Also extract text from Word tables.
        for table in document.tables:
            for row in table.rows:
                parts.append(
                    " | ".join(cell.text for cell in row.cells)
                )

        return "\n".join(parts)

    if extension == ".md":
        return file_path.read_text(encoding="utf-8-sig")

    if extension == ".csv":
        rows = []

        with file_path.open(
            "r",
            encoding="utf-8-sig",
            newline=""
        ) as csv_file:
            reader = csv.reader(csv_file)

            for row in reader:
                rows.append(" | ".join(row))

        return "\n".join(rows)

    raise ValueError("Unsupported document format.")


async def store_and_extract_upload(
    upload: UploadFile,
    project_id: int
) -> dict:
    """Save an uploaded file safely and extract its text."""

    file_path = None

    try:
        if not upload.filename:
            raise HTTPException(
                status_code=400,
                detail="A filename is required."
            )

        # Remove any directory components from the supplied filename.
        original_filename = (
            upload.filename.replace("\\", "/").split("/")[-1].strip()
        )

        if not original_filename or len(original_filename) > 255:
            raise HTTPException(
                status_code=400,
                detail="Invalid filename."
            )

        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail="Only PDF, DOCX, Markdown and CSV files are supported."
            )

        # Never use the supplied filename as the physical storage filename.
        stored_filename = f"{uuid4().hex}{extension}"

        project_directory = STORAGE_ROOT / str(project_id)
        project_directory.mkdir(parents=True, exist_ok=True)

        file_path = project_directory / stored_filename

        sha256 = hashlib.sha256()
        total_size = 0

        # Stream the upload in chunks instead of loading it all into memory.
        with file_path.open("xb") as destination:
            while True:
                chunk = await upload.read(CHUNK_SIZE)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_UPLOAD_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 20 MB upload limit."
                    )

                sha256.update(chunk)
                destination.write(chunk)

        if total_size == 0:
            raise HTTPException(
                status_code=400,
                detail="The uploaded file is empty."
            )

        # Basic file signature checks.
        with file_path.open("rb") as source:
            header = source.read(1024)

        if extension == ".pdf" and b"%PDF-" not in header:
            raise HTTPException(
                status_code=415,
                detail="The file does not appear to be a valid PDF."
            )

        if extension == ".docx" and not zipfile.is_zipfile(file_path):
            raise HTTPException(
                status_code=415,
                detail="The file does not appear to be a valid DOCX document."
            )

        # Extract the text before registering the document.
        extracted_text = extract_document_text(file_path, extension)

        return {
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "file_type": extension.lstrip("."),
            "mime_type": (upload.content_type or "application/octet-stream")[:150],
            "file_path": str(file_path),
            "size_bytes": total_size,
            "sha256": sha256.hexdigest(),
            "extraction_status": "processed",
            "extracted_text": extracted_text,
        }

    except HTTPException:
        if file_path and file_path.exists():
            file_path.unlink(missing_ok=True)
        raise

    except Exception as exc:
        logger.exception("Document upload or extraction failed.")

        if file_path and file_path.exists():
            file_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=422,
            detail="The document could not be read. Check that the file is valid and not corrupted."
        ) from exc

    finally:
        await upload.close()


def delete_stored_file(file_path: str) -> None:
    """Remove a stored file if database registration fails."""

    path = Path(file_path)

    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not remove failed upload: %s", path)