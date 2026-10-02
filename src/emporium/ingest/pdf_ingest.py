import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from emporium.db import models
from emporium.ingest.chunking import chunk_policy, detect_source_version, extract_pdf_text


def find_policy_pdf(raw_data_dir: Path) -> Path:
    pdfs = list(raw_data_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No policy PDF found in {raw_data_dir}")
    return pdfs[0]


async def ingest_policy(
    engine: AsyncEngine,
    embedder,
    raw_data_dir: Path,
) -> dict[str, object]:
    pdf_path = find_policy_pdf(raw_data_dir)
    full_text = extract_pdf_text(pdf_path)
    source_version = detect_source_version(full_text)
    chunks = chunk_policy(full_text)

    embed_texts = [f"{chunk.title}. {chunk.text}" for chunk in chunks]
    vectors = await asyncio.to_thread(embedder.embed_documents, embed_texts)

    rows = [
        {
            "source_version": source_version,
            "section": chunk.section,
            "title": chunk.title,
            "text": chunk.text,
            "embedding": vector,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE policy_chunks RESTART IDENTITY CASCADE"))
        if rows:
            await conn.execute(pg_insert(models.PolicyChunk.__table__).values(rows))

    return {"source_version": source_version, "chunks": len(rows)}
