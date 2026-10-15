import psycopg

from forge import embeddings


async def vector_search(conn: psycopg.AsyncConnection, query: str, k: int = 5) -> list[dict]:
    vector = embeddings.embed_query(query)
    cur = await conn.execute(
        """SELECT id, section_path, pdf_page_start, pdf_page_end, text,
                  1 - (embedding <=> %(v)s) AS score
           FROM chunks
           ORDER BY embedding <=> %(v)s
           LIMIT %(k)s""",
        {"v": vector, "k": k},
    )
    return await cur.fetchall()
