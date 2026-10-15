from typing import Literal

from fastapi import FastAPI, HTTPException, Query

from forge.db import connect
from forge.lessons import GenerationError, LessonRequest, create_lesson, get_lesson
from forge.llm import LLMError
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


@app.post("/lessons", status_code=201)
async def new_lesson(request: LessonRequest):
    # Takes 20-40 s. Fine for a demo; a job queue comes when the deployment needs it.
    async with await connect() as conn:
        try:
            return await create_lesson(conn, request)
        except GenerationError as e:
            raise HTTPException(502, f"the model's answer didn't pass validation: {e}") from e
        except LLMError as e:
            raise HTTPException(503, f"the model call failed: {e}") from e


@app.get("/lessons")
async def list_lessons(limit: int = Query(20, ge=1, le=100)):
    async with await connect() as conn:
        cur = await conn.execute(
            """SELECT id, status, request->>'topic' AS topic, lesson->>'title' AS title, created_at
               FROM lessons ORDER BY id DESC LIMIT %s""",
            [limit],
        )
        return await cur.fetchall()


@app.get("/lessons/{lesson_id}")
async def lesson(lesson_id: int):
    async with await connect() as conn:
        if found := await get_lesson(conn, lesson_id):
            return found
    raise HTTPException(404, "lesson not found")
