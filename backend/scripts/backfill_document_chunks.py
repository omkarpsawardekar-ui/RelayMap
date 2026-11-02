from sqlalchemy import func

from app.db.session import SessionLocal
from app.models import Document, DocumentChunk
from app.services.chunking_services import build_document_chunks


def main():
    db = SessionLocal()

    processed = 0
    skipped = 0
    failed = 0

    try:
        documents = (
            db.query(Document)
            .order_by(Document.id.asc())
            .all()
        )

        print(f"Found {len(documents)} documents.")

        for document in documents:

            existing_count = (
                db.query(func.count(DocumentChunk.id))
                .filter(
                    DocumentChunk.document_id == document.id
                )
                .scalar()
            )

            if existing_count:
                print(
                    f"SKIPPED document {document.id}: "
                    f"already has {existing_count} chunks."
                )
                skipped += 1
                continue

            try:
                chunks = build_document_chunks(
                    file_path=document.file_path,
                    file_type=document.file_type,
                    fallback_text=document.extracted_text,
                )

                records = [
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=chunk["chunk_index"],
                        source_locator=chunk["source_locator"],
                        chunk_text=chunk["chunk_text"],
                        content_sha256=chunk["content_sha256"],
                    )
                    for chunk in chunks
                ]

                db.add_all(records)
                db.commit()

                print(
                    f"SUCCESS document {document.id}: "
                    f"created {len(records)} chunks."
                )

                processed += 1

            except Exception as exc:
                db.rollback()

                print(
                    f"FAILED document {document.id}: {exc}"
                )

                failed += 1

        print("\nBACKFILL SUMMARY")
        print("Processed:", processed)
        print("Skipped:", skipped)
        print("Failed:", failed)

    finally:
        db.close()


if __name__ == "__main__":
    main()