"""Parse the book, chunk it, embed the chunks and load everything into Postgres.

Usage: uv run python -m forge.ingest [path/to/psychology-2e.pdf]
"""

import hashlib
import sys
import time
from pathlib import Path

from forge import embeddings
from forge.book import BOOK, DEFAULT_PDF, KNOWN_SHA256, load_sections
from forge.chunking import chunk_section
from forge.db import connect, run


def text_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


async def ingest(pdf: Path) -> None:
    started = time.perf_counter()
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if digest != KNOWN_SHA256:
        print(f"warning: {pdf.name} is not the copy listed in docs/corpus.md", file=sys.stderr)

    sections = load_sections(pdf)
    chunks = [c for s in sections for c in chunk_section(s, embeddings.count_tokens)]

    async with await connect() as conn:
        # Re-running is cheap: embeddings for text we've seen before are reused.
        rows = await conn.execute(
            "SELECT md5(text) AS hash, embedding FROM chunks WHERE embedding_model = %s",
            [embeddings.MODEL],
        )
        known = {row["hash"]: row["embedding"] for row in await rows.fetchall()}
        missing = list({c.text for c in chunks if text_hash(c.text) not in known})
        known.update(zip(map(text_hash, missing), embeddings.embed(missing), strict=True))

        await conn.execute("DELETE FROM documents WHERE content_hash = %s", [digest])
        cur = await conn.execute(
            """INSERT INTO documents (title, authors, source_url, license, license_url, attribution,
                                      content_hash)
               VALUES (%(title)s, %(authors)s, %(source_url)s, %(license)s, %(license_url)s,
                       %(attribution)s, %(content_hash)s)
               RETURNING id""",
            {**BOOK, "content_hash": digest},
        )
        document_id = (await cur.fetchone())["id"]
        async with conn.cursor() as cur:
            await cur.executemany(
                """INSERT INTO chunks (document_id, ordinal, section_path, pdf_page_start, pdf_page_end,
                                       text, token_count, embedding, embedding_model)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        document_id,
                        i,
                        c.section_path,
                        c.pdf_page_start,
                        c.pdf_page_end,
                        c.text,
                        c.token_count,
                        known[text_hash(c.text)],
                        embeddings.MODEL,
                    )
                    for i, c in enumerate(chunks)
                ],
            )
        await conn.commit()

    tokens = [c.token_count for c in chunks]
    print(f"{BOOK['title']} ({BOOK['license']}), sha256 {digest[:12]}")
    print(
        f"{len(sections)} sections -> {len(chunks)} chunks, tokens min {min(tokens)} "
        f"avg {sum(tokens) // len(tokens)} max {max(tokens)}"
    )
    print(
        f"embedded {len(missing)} new chunks, reused {len(chunks) - len(missing)}, "
        f"{time.perf_counter() - started:.1f}s"
    )


def main() -> None:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf.exists():
        sys.exit(f"{pdf} not found. See docs/corpus.md for how to download it.")
    run(ingest(pdf))


if __name__ == "__main__":
    main()
