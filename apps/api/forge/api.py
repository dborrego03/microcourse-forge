from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse

from forge.cmi5 import build_cmi5
from forge.db import connect
from forge.guardrails import Blocked
from forge.lessons import GenerationError, LessonRequest, create_lesson, get_lesson
from forge.llm import LLMError
from forge.scorm import build_scorm12, package_name
from forge.search import SEARCH_MODES
from forge.tts import MEDIA_DIR, TTSError, narrate

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
        except Blocked as e:
            raise HTTPException(422, {"rule": e.rule, "message": str(e)}) from e
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


PACKAGES = {"scorm": ("scorm12", build_scorm12), "cmi5": ("cmi5", build_cmi5)}


@app.get("/lessons/{lesson_id}/{kind}")
async def lesson_package(lesson_id: int, kind: Literal["scorm", "cmi5"]):
    async with await connect() as conn:
        found = await get_lesson(conn, lesson_id)
    if not found or found["status"] != "ready":
        raise HTTPException(404, "no ready lesson with that id")
    name, build = PACKAGES[kind]
    return Response(
        build(found, MEDIA_DIR / f"lesson-{lesson_id}"),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{package_name(found, name)}"'},
    )


@app.post("/lessons/{lesson_id}/audio")
async def narrate_lesson(lesson_id: int):
    async with await connect() as conn:
        found = await get_lesson(conn, lesson_id)
        if not found or found["status"] != "ready":
            raise HTTPException(404, "no ready lesson with that id")
        try:
            return await narrate(conn, found)
        except TTSError as e:
            raise HTTPException(503, str(e)) from e


@app.get("/media/lesson-{lesson_id}/part-{part}.{ext}")
async def media(lesson_id: int, part: int, ext: Literal["mp3", "vtt"]):
    # Ints and a fixed extension, so the path can't point outside the media folder.
    path = MEDIA_DIR / f"lesson-{lesson_id}" / f"part-{part}.{ext}"
    if not path.exists():
        raise HTTPException(404, "no such file")
    return FileResponse(path, media_type="audio/mpeg" if ext == "mp3" else "text/vtt")
