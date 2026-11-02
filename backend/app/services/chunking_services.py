
import csv
import hashlib

from pathlib import Path

import fitz
from docx import Document as WordDocument


MAX_CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150


def normalize_text(text: str) -> str:
    """Normalize extracted text without removing meaningful content."""

    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    return text.strip()


def split_text(text: str) -> list[str]:
    """Split long text into overlapping, readable chunks."""

    text = normalize_text(text)

    if not text:
        return []

    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        hard_end = min(start + MAX_CHUNK_CHARS, len(text))
        end = hard_end

        if hard_end < len(text):
            window = text[start:hard_end]

            # Prefer splitting at a natural text boundary.
            boundaries = [
                window.rfind("\n"),
                window.rfind(". "),
                window.rfind(" "),
                window.rfind("\t"),
            ]

            boundary = max(boundaries)

            if boundary >= MAX_CHUNK_CHARS * 0.55:
                end = start + boundary + 1

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        # Preserve a small overlap between consecutive chunks.
        start = max(start + 1, end - CHUNK_OVERLAP)

        while start < len(text) and text[start].isspace():
            start += 1

    return chunks


def extract_pdf_segments(file_path: Path) -> list[tuple[str, str]]:
    """Extract text separately from every PDF page."""

    segments = []

    with fitz.open(str(file_path)) as pdf:
        if pdf.is_encrypted and not pdf.authenticate(""):
            raise ValueError("Password-protected PDFs are not supported.")

        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text("text")

            if text.strip():
                segments.append((f"page:{page_number}", text))

    return segments


def extract_docx_segments(file_path: Path) -> list[tuple[str, str]]:
    """Extract Word paragraphs and table rows."""

    document = WordDocument(str(file_path))
    segments = []

    for paragraph_number, paragraph in enumerate(
        document.paragraphs,
        start=1
    ):
        if paragraph.text.strip():
            segments.append(
                (f"paragraph:{paragraph_number}", paragraph.text)
            )

    for table_number, table in enumerate(document.tables, start=1):
        for row_number, row in enumerate(table.rows, start=1):
            row_text = " | ".join(
                cell.text.strip() for cell in row.cells
            )

            if row_text.strip():
                locator = f"table:{table_number},row:{row_number}"
                segments.append((locator, row_text))

    return segments


def extract_markdown_segments(file_path: Path) -> list[tuple[str, str]]:
    """Extract Markdown paragraphs while preserving line numbers."""

    lines = file_path.read_text(
        encoding="utf-8-sig"
    ).splitlines()

    segments = []

    current_lines = []
    start_line = None

    def save_paragraph(end_line: int):
        nonlocal current_lines, start_line

        if current_lines:
            locator = f"lines:{start_line}-{end_line}"

            segments.append(
                (locator, "\n".join(current_lines))
            )

        current_lines = []
        start_line = None

    for line_number, line in enumerate(lines, start=1):
        if line.strip():
            if start_line is None:
                start_line = line_number

            current_lines.append(line)
        else:
            save_paragraph(line_number - 1)

    save_paragraph(len(lines))

    return segments


def extract_csv_segments(file_path: Path) -> list[tuple[str, str]]:
    """Extract CSV records while preserving row numbers and headers."""

    segments = []

    with file_path.open(
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as csv_file:

        reader = csv.reader(csv_file)
        rows = list(reader)

    if not rows:
        return segments

    header = " | ".join(rows[0])

    if len(rows) == 1:
        segments.append(("row:1", header))
        return segments

    for row_number, row in enumerate(rows[1:], start=2):
        row_text = " | ".join(row)

        content = (
            f"Header: {header}\n"
            f"Row: {row_text}"
        )

        segments.append(
            (f"row:{row_number}", content)
        )

    return segments


def build_document_chunks(
    file_path: str,
    file_type: str,
    fallback_text: str | None = None,
) -> list[dict]:
    """
    Create evidence-aware chunks from an uploaded document.

    Every chunk retains its original source locator.
    """

    path = Path(file_path)
    extension = file_type.lower().lstrip(".")

    if path.exists():

        if extension == "pdf":
            segments = extract_pdf_segments(path)

        elif extension == "docx":
            segments = extract_docx_segments(path)

        elif extension == "md":
            segments = extract_markdown_segments(path)

        elif extension == "csv":
            segments = extract_csv_segments(path)

        else:
            raise ValueError(
                f"Unsupported document type: {extension}"
            )

    elif fallback_text and fallback_text.strip():

        # Fallback for previously extracted documents
        # whose original file is no longer available.
        segments = [
            ("document:stored_extracted_text", fallback_text)
        ]

    else:
        raise FileNotFoundError(
            f"Document file not found: {path}"
        )

    chunk_records = []
    chunk_index = 0

    for source_locator, segment_text in segments:

        split_chunks = split_text(segment_text)
        total_parts = len(split_chunks)

        for part_number, chunk_text in enumerate(
            split_chunks,
            start=1
        ):
            chunk_index += 1

            if total_parts > 1:
                locator = (
                    f"{source_locator},part:{part_number}/{total_parts}"
                )
            else:
                locator = source_locator

            content_hash = hashlib.sha256(
                chunk_text.encode("utf-8")
            ).hexdigest()

            chunk_records.append({
                "chunk_index": chunk_index,
                "source_locator": locator[:120],
                "chunk_text": chunk_text,
                "content_sha256": content_hash,
            })

    if not chunk_records:
        raise ValueError(
            "No readable text was found in this document."
        )

    return chunk_records