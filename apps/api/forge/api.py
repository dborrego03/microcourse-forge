from typing import Literal

from fastapi import FastAPI, Query

from forge.db import connect
from forge.search import SEARCH_MODES

app = FastAPI(title="microcourse-forge")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/search")
async def search(
    q: str = Query(min_length=3, max_length=300),
    k: int = Query(5, ge=1, le=20),
    mode: Literal["vector", "hybrid", "rerank"] = "rerank",
):
    async with await connect() as conn:
        return await SEARCH_MODES[mode](conn, q, k)
