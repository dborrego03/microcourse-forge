"""Three ways to retrieve chunks, so they can be compared in evals.

- vector: cosine distance on bge-small embeddings (HNSW index)
- hybrid: vector + full-text ranking merged with reciprocal rank fusion (RRF)
- rerank: hybrid candidates re-ordered by a small cross-encoder
"""

import asyncio

import psycopg

from forge import embeddings

COLUMNS = "c.id, c.section_path, c.pdf_page_start, c.pdf_page_end, c.text"
RRF_K = 60  # the usual constant from the original RRF paper
HYBRID_POOL = 20  # candidates taken from each ranking before fusing
# On retrieval_v1, 20 candidates gave MRR 0.891 at ~1.7 s p50 and 10 gave 0.878 at ~1.0 s.
RERANK_CANDIDATES = 10


async def vector_search(conn: psycopg.AsyncConnection, query: str, k: int = 5) -> list[dict]:
    cur = await conn.execute(
        f"""SELECT {COLUMNS}, 1 - (c.embedding <=> %(v)s) AS score
            FROM chunks c
            ORDER BY c.embedding <=> %(v)s
            LIMIT %(k)s""",
        {"v": await asyncio.to_thread(embeddings.embed_query, query), "k": k},
    )
    return await cur.fetchall()


async def hybrid_search(conn: psycopg.AsyncConnection, query: str, k: int = 5) -> list[dict]:
    # plainto_tsquery ANDs every word, which almost never matches a full question,
    # so the terms are OR-ed and ts_rank_cd rewards chunks that match more of them.
    cur = await conn.execute(
        f"""WITH q AS (
                SELECT replace(plainto_tsquery('english', %(q)s)::text, '&', '|')::tsquery AS query
            ),
            by_vector AS (
                SELECT id, row_number() OVER (ORDER BY embedding <=> %(v)s) AS rank
                FROM chunks ORDER BY embedding <=> %(v)s LIMIT %(n)s
            ),
            by_text AS (
                SELECT id, row_number() OVER (ORDER BY ts_rank_cd(tsv, q.query) DESC) AS rank
                FROM chunks, q WHERE tsv @@ q.query
                ORDER BY ts_rank_cd(tsv, q.query) DESC LIMIT %(n)s
            )
            SELECT {COLUMNS},
                   coalesce(1.0 / ({RRF_K} + v.rank), 0) + coalesce(1.0 / ({RRF_K} + t.rank), 0) AS score
            FROM chunks c
            LEFT JOIN by_vector v ON v.id = c.id
            LEFT JOIN by_text t ON t.id = c.id
            WHERE v.id IS NOT NULL OR t.id IS NOT NULL
            ORDER BY score DESC
            LIMIT %(k)s""",
        {"q": query, "v": await asyncio.to_thread(embeddings.embed_query, query), "n": HYBRID_POOL, "k": k},
    )
    return await cur.fetchall()


async def rerank_search(conn: psycopg.AsyncConnection, query: str, k: int = 5) -> list[dict]:
    candidates = await hybrid_search(conn, query, RERANK_CANDIDATES)
    # ONNX inference is CPU-bound; off the event loop it doesn't stall other requests.
    scores = await asyncio.to_thread(embeddings.rerank, query, [c["text"] for c in candidates])
    ranked = sorted(zip(scores, candidates, strict=True), key=lambda pair: pair[0], reverse=True)
    return [{**c, "score": float(score)} for score, c in ranked[:k]]


SEARCH_MODES = {"vector": vector_search, "hybrid": hybrid_search, "rerank": rerank_search}
