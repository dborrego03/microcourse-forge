"""Generate a cited lesson and a quiz from retrieved chunks."""

import asyncio
import hashlib
import os
import random
import re
import time
from pathlib import Path
from typing import Literal

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from forge.guardrails import check_scope, check_text, moderate
from forge.llm import LLMResult, complete_json
from forge.search import rerank_search
from forge.version import git_sha

PROMPTS = Path(__file__).parent / "prompts"
# Full model ids instead of aliases, so a model update can't silently change results.
GENERATOR_MODEL = os.environ.get("FORGE_GENERATOR_MODEL", "claude-haiku-5-5")
SOURCES_PER_LESSON = 6


def load_prompt(name: str) -> tuple[str, str]:
    """Prompt text and a version tag derived from it, so the tag can't go stale."""
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    return text, f"{name}-{hashlib.sha256(text.encode()).hexdigest()[:8]}"


class LessonRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    objectives: list[str] = Field(default=[], max_length=4)
    level: Literal["beginner", "intermediate"] = "beginner"

    @field_validator("objectives")
    @classmethod
    def objectives_are_short(cls, value: list[str]) -> list[str]:
        if any(not 3 <= len(o) <= 200 for o in value):
            raise ValueError("each objective must be 3-200 characters")
        return value


class LessonSection(BaseModel):
    heading: str
    body: str
    example: str | None = None
    sources: list[int] = Field(min_length=1)


class Lesson(BaseModel):
    title: str
    objectives: list[str] = Field(min_length=2, max_length=4)
    sections: list[LessonSection] = Field(min_length=3, max_length=5)
    summary: str


class Question(BaseModel):
    objective: int = Field(ge=1)
    type: Literal["multiple_choice", "true_false", "short_answer"]
    question: str
    options: list[str] = []
    answer: str
    feedback: str
    source: int

    @model_validator(mode="after")
    def options_match_type(self):
        if self.type == "multiple_choice" and len(self.options) != 4:
            raise ValueError("multiple_choice needs exactly 4 options")
        if self.type == "true_false" and self.options != ["True", "False"]:
            raise ValueError('true_false options must be ["True", "False"]')
        if self.type == "short_answer" and self.options:
            raise ValueError("short_answer has no options")
        if self.options and self.answer not in self.options:
            raise ValueError("answer must be one of the options")
        return self


class Quiz(BaseModel):
    questions: list[Question] = Field(min_length=4, max_length=6)


class GenerationError(Exception):
    pass


def format_sources(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        # A chunk can't close its own tag and smuggle text outside the data block.
        text = re.sub(r"</?source", "", c["text"], flags=re.IGNORECASE)
        parts.append(
            f'<source id="{c["id"]}" section="{c["section_path"]}" '
            f'pages="{c["pdf_page_start"]}-{c["pdf_page_end"]}">\n{text}\n</source>'
        )
    return "<sources>\n" + "\n".join(parts) + "\n</sources>"


def lesson_problems(lesson: Lesson, source_ids: set[int]) -> list[str]:
    unknown = {s for section in lesson.sections for s in section.sources} - source_ids
    return [f"sections cite sources that were not provided: {sorted(unknown)}"] if unknown else []


def quiz_problems(quiz: Quiz, lesson: Lesson, source_ids: set[int]) -> list[str]:
    problems = []
    count = len(lesson.objectives)
    if bad := [q.objective for q in quiz.questions if q.objective > count]:
        problems.append(f"objective numbers {bad} don't exist (the lesson has {count})")
    if missing := set(range(1, count + 1)) - {q.objective for q in quiz.questions}:
        problems.append(f"objectives {sorted(missing)} have no question")
    if unknown := {q.source for q in quiz.questions} - source_ids:
        problems.append(f"questions cite sources that were not provided: {sorted(unknown)}")
    for i, q in enumerate(quiz.questions, 1):
        if q.type == "multiple_choice" and len(q.answer) > 3 and q.answer.lower() in q.question.lower():
            problems.append(f"question {i} gives its answer away in the question text")
    return problems


def shuffle_options(quiz: Quiz) -> None:
    # Models tend to put the right answer first. A fixed seed per question keeps
    # the order stable when the same quiz is loaded again from the cache.
    for q in quiz.questions:
        if q.type == "multiple_choice":
            random.Random(q.question).shuffle(q.options)


def generate(model_cls, system: str, prompt: str, check) -> tuple[BaseModel, LLMResult, int]:
    """One call, plus one retry that shows the model what was wrong. Returns (value, last call, retries)."""
    schema = model_cls.model_json_schema()
    result = complete_json(system, prompt, schema, GENERATOR_MODEL)
    for retry in (0, 1):
        try:
            value = model_cls.model_validate(result.data)
            problems = check(value)
        except ValidationError as e:
            problems = [str(e)]
        if not problems:
            return value, result, retry
        if retry == 1:
            break
        feedback = "\n".join(f"- {p}" for p in problems)
        retry_prompt = f"{prompt}\n\nYour previous answer had these problems. Fix them:\n{feedback}"
        result = complete_json(system, retry_prompt, schema, GENERATOR_MODEL)
    raise GenerationError("; ".join(problems))


async def log_run(conn, lesson_id, step, started, result=None, retries=0, error=None) -> None:
    await conn.execute(
        """INSERT INTO runs (lesson_id, step, status, model, tokens_in, tokens_out, cost_usd,
                             latency_ms, retries, cached, error, git_sha)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        [
            lesson_id, step, "error" if error else "ok",
            result.model if result else None,
            result.tokens_in if result else 0,
            result.tokens_out if result else 0,
            result.cost_usd if result else 0,
            round((time.perf_counter() - started) * 1000), retries,
            result.cached if result else False, error, git_sha(),
        ],
    )  # fmt: skip


async def create_lesson(conn: psycopg.AsyncConnection, request: LessonRequest) -> dict:
    # Guardrails run before anything is stored, so a blocked request (which may
    # contain personal data) never reaches the database or the model.
    check_text(request.topic, *request.objectives)
    started = time.perf_counter()
    chunks = await rerank_search(conn, " ".join([request.topic, *request.objectives]), SOURCES_PER_LESSON)
    check_scope(chunks[0]["score"] if chunks else float("-inf"))
    await asyncio.to_thread(moderate, request.topic, request.objectives)

    cur = await conn.execute(
        "INSERT INTO lessons (request, status) VALUES (%s, 'running') RETURNING id",
        [Jsonb(request.model_dump())],
    )
    lesson_id = (await cur.fetchone())["id"]
    await log_run(conn, lesson_id, "retrieve", started)
    await conn.commit()
    try:
        source_ids = {c["id"] for c in chunks}
        sources = format_sources(chunks)
        lesson_system, lesson_version = load_prompt("lesson")
        quiz_system, quiz_version = load_prompt("quiz")

        step, started = "lesson", time.perf_counter()
        wanted = "\n".join(f"- {o}" for o in request.objectives) or "(choose them from the sources)"
        lesson, result, retries = await asyncio.to_thread(
            generate,
            Lesson,
            lesson_system,
            f"Topic: {request.topic}\nLevel: {request.level}\nObjectives wanted:\n{wanted}\n\n{sources}",
            lambda value: lesson_problems(value, source_ids),
        )
        await log_run(conn, lesson_id, step, started, result, retries)

        step, started = "quiz", time.perf_counter()
        quiz, result, retries = await asyncio.to_thread(
            generate,
            Quiz,
            quiz_system,
            f"Lesson:\n{lesson.model_dump_json(indent=1)}\n\n{sources}",
            lambda value: quiz_problems(value, lesson, source_ids),
        )
        shuffle_options(quiz)
        await log_run(conn, lesson_id, step, started, result, retries)
    except Exception as e:
        await log_run(conn, lesson_id, step, started, error=str(e)[:500])
        await conn.execute("UPDATE lessons SET status = 'failed' WHERE id = %s", [lesson_id])
        await conn.commit()
        raise

    await conn.execute(
        """UPDATE lessons SET status = 'ready', lesson = %s, quiz = %s, source_chunk_ids = %s,
                              model = %s, prompt_version = %s
           WHERE id = %s""",
        [
            Jsonb(lesson.model_dump()), Jsonb(quiz.model_dump()), sorted(source_ids),
            GENERATOR_MODEL, f"{lesson_version}+{quiz_version}", lesson_id,
        ],
    )  # fmt: skip
    await conn.commit()
    return await get_lesson(conn, lesson_id)


async def get_lesson(conn: psycopg.AsyncConnection, lesson_id: int) -> dict | None:
    cur = await conn.execute(
        """SELECT l.id, l.status, l.request, l.lesson, l.quiz, l.model, l.prompt_version, l.created_at,
                  coalesce(json_agg(json_build_object(
                      'id', c.id, 'section', c.section_path,
                      'pages', c.pdf_page_start || '-' || c.pdf_page_end,
                      'text', c.text, 'title', d.title, 'license', d.license, 'license_url', d.license_url,
                      'attribution', d.attribution, 'source_url', d.source_url
                  ) ORDER BY c.id) FILTER (WHERE c.id IS NOT NULL), '[]') AS sources
           FROM lessons l
           LEFT JOIN chunks c ON c.id = ANY (l.source_chunk_ids)
           LEFT JOIN documents d ON d.id = c.document_id
           WHERE l.id = %s
           GROUP BY l.id""",
        [lesson_id],
    )
    return await cur.fetchone()
