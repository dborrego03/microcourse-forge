from forge import embeddings
from forge.search import vector_search

TEXTS = [
    "Pavlov paired a tone with meat powder until the tone alone made the dogs salivate.",
    "Working memory holds a small amount of information for a short time.",
    "IQ tests compare a person's score with the scores of others of the same age.",
]


async def add_chunks(conn, texts):
    cur = await conn.execute(
        """INSERT INTO documents (title, authors, source_url, license, license_url, attribution, content_hash)
           VALUES ('Test', 'Me', 'http://example.com', 'CC0', 'http://example.com', 'none', 'test-hash')
           RETURNING id"""
    )
    document_id = (await cur.fetchone())["id"]
    for i, (text, vector) in enumerate(zip(texts, embeddings.embed(texts), strict=True)):
        await conn.execute(
            """INSERT INTO chunks (document_id, ordinal, section_path, pdf_page_start, pdf_page_end,
                                   text, token_count, embedding, embedding_model)
               VALUES (%s, %s, 'Test > Section', 1, 1, %s, 10, %s, %s)""",
            [document_id, i, text, vector, embeddings.MODEL],
        )
    await conn.execute("DELETE FROM chunks WHERE document_id <> %s", [document_id])


async def test_vector_search_ranks_the_matching_chunk_first(conn):
    await add_chunks(conn, TEXTS)

    results = await vector_search(conn, "How did Pavlov condition his dogs?", k=3)

    assert results[0]["text"] == TEXTS[0]
    assert results[0]["score"] > results[1]["score"]
