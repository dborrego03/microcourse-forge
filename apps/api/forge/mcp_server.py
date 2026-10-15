"""MCP server that exposes the pipeline as tools.

    uv run python -m forge.mcp_server     (stdio; add it to an MCP client such as Claude Desktop)

Generation, judging and export are the same code the API uses, so guardrails,
validation, caching and run logging all apply. Side effects are marked in the
tool annotations so a client can ask before calling them.
"""

import asyncio
import json
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from forge import REPO_ROOT
from forge.db import connect, run
from forge.judge import CRITERIA, review_lesson
from forge.lessons import LessonRequest, create_lesson, get_lesson
from forge.scorm import build_scorm12, package_name
from forge.search import rerank_search
from forge.tts import MEDIA_DIR

EXPORT_DIR = REPO_ROOT / "data" / "exports"

server = MCPServer(
    "microcourse-forge",
    instructions=(
        "Tools for writing short psychology lessons from OpenStax Psychology 2e (chapters on learning, "
        "thinking and memory). Search the sources first, generate one lesson per topic, evaluate it, and "
        "only export after the user has approved the lesson."
    ),
)


@server.tool(annotations=ToolAnnotations(read_only_hint=True))
async def search_sources(query: str, k: int = 5) -> list[dict]:
    """Find passages of the book relevant to a question or topic (k between 1 and 10)."""
    async with await connect() as conn:
        rows = await rerank_search(conn, query[:300], max(1, min(k, 10)))
    return [
        {
            "id": r["id"],
            "section": r["section_path"],
            "pdf_pages": f"{r['pdf_page_start']}-{r['pdf_page_end']}",
            "text": r["text"],
        }
        for r in rows
    ]


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True))
async def generate_lesson(
    topic: str, objectives: list[str] | None = None, level: Literal["beginner", "intermediate"] = "beginner"
) -> dict:
    """Write a cited lesson and quiz on a topic from the book. Takes 20-60 seconds."""
    request = LessonRequest(topic=topic, objectives=objectives or [], level=level)
    async with await connect() as conn:
        lesson = await create_lesson(conn, request)
    return {
        "lesson_id": lesson["id"],
        "title": lesson["lesson"]["title"],
        "objectives": lesson["lesson"]["objectives"],
    }


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
async def evaluate_lesson(lesson_id: int) -> dict:
    """Have a judge model check a lesson: claims backed by its sources, relevance, rubric scores."""
    async with await connect() as conn:
        lesson = await get_lesson(conn, lesson_id)
    if not lesson or lesson["status"] != "ready":
        raise ValueError(f"no ready lesson with id {lesson_id}")
    review, _ = await asyncio.to_thread(review_lesson, lesson)
    claims = review.claims
    return {
        "faithfulness": round(sum(c.supported for c in claims) / len(claims), 3) if claims else None,
        "unsupported_claims": [c.claim for c in claims if not c.supported],
        "relevance": review.relevance.score,
        "rubric": {name: getattr(review, name).score for name in CRITERIA},
    }


@server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True))
async def export_package(lesson_id: int) -> dict:
    """Write the lesson as a SCORM 1.2 zip under data/exports and return its path. Ask the user first."""
    async with await connect() as conn:
        lesson = await get_lesson(conn, lesson_id)
    if not lesson or lesson["status"] != "ready":
        raise ValueError(f"no ready lesson with id {lesson_id}")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / package_name(lesson)
    path.write_bytes(build_scorm12(lesson, MEDIA_DIR / f"lesson-{lesson_id}"))
    return {"path": str(path), "size_bytes": path.stat().st_size}


@server.resource("lesson://{lesson_id}", mime_type="application/json")
async def lesson_resource(lesson_id: str) -> str:
    """A generated lesson with its quiz and sources."""
    async with await connect() as conn:
        lesson = await get_lesson(conn, int(lesson_id))
    return json.dumps(lesson, default=str)


if __name__ == "__main__":
    run(server.run_stdio_async())
