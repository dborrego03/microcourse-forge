"""Parse the book, chunk it, embed the chunks and load everything into Postgres.

Usage: uv run python -m forge.ingest [path/to/psychology-2e.pdf | --url URL]
"""

import argparse
import hashlib
import sys
import tempfile
import time
from pathlib import Path

import httpx

from forge import embeddings
from forge.book import BOOK, DEFAULT_PDF, KNOWN_SHA256, load_sections
from forge.chunking import chunk_section
from forge.db import connect, run


def text_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


async def ingest(pdf: Path, force: bool = False) -> None:
    started = time.perf_counter()
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if digest != KNOWN_SHA256:
        print(f"warning: {pdf.name} is not the copy listed in docs/corpus.md", file=sys.stderr)

    # Reloading replaces every chunk id, and lessons cite chunks by id, so it is opt-in.
    async with await connect() as conn:
        cur = await conn.execute("SELECT id FROM documents WHERE content_hash = %s", [digest])
        if not force and await cur.fetchone():
            print("already loaded; pass --force to reload (existing lessons lose their citations)")
            return

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


def download(url: str) -> Path:
    """Fetch the PDF into a temp file and refuse anything but the copy the evals were labelled on."""
    path = Path(tempfile.gettempdir()) / "psychology-2e.pdf"
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as res:
        res.raise_for_status()
        with path.open("wb") as f:
            for block in res.iter_bytes():
                f.write(block)
    if hashlib.sha256(path.read_bytes()).hexdigest() != KNOWN_SHA256:
        sys.exit(f"{url} doesn't match the SHA-256 in docs/corpus.md; refusing to ingest it")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Load chapters 6-8 of the book into Postgres.")
    parser.add_argument("pdf", nargs="?", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--url", help="download the PDF first (used by the container job)")
    parser.add_argument("--force", action="store_true", help="reload even if this copy is already loaded")
    args = parser.parse_args()

    pdf = download(args.url) if args.url else args.pdf
    if not pdf.exists():
        sys.exit(f"{pdf} not found. See docs/corpus.md for how to download it.")
    run(ingest(pdf, args.force))


if __name__ == "__main__":
    main()
