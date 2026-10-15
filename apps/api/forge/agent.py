"""A bounded course agent: the model plans, the code does the rest.

    uv run python -m forge.agent "An introduction to how memory works" [--lessons 3] [--yes]

1. The model turns a goal into a plan of 2-5 lessons, each tied to a section of the book.
2. A person approves the plan.
3. Each lesson goes through the normal pipeline (guardrails, generation, validation)
   and is reviewed by the judge.
4. A person approves the export of the lessons that meet the quality bar, as one
   cmi5 course.

Only step 1 is model-driven, and the code enforces the limits: a fixed number of
lessons, a spending cap and a time cap, checked before every lesson. There is no
open-ended tool loop, so it can't run away.
"""

import argparse
import asyncio
import os
import sys
import time
from collections.abc import Callable

from pydantic import BaseModel, Field

from forge import REPO_ROOT
from forge.cmi5 import build_cmi5_course
from forge.db import connect, run
from forge.guardrails import Blocked, check_text
from forge.judge import CRITERIA, review_lesson
from forge.lessons import GenerationError, LessonRequest, create_lesson, generate, load_prompt
from forge.llm import LLMError
from forge.tts import MEDIA_DIR

MAX_LESSONS = 5
BUDGET_USD = float(os.environ.get("FORGE_AGENT_BUDGET_USD", "0.50"))  # API-price estimate
TIME_LIMIT_S = 20 * 60
MIN_FAITHFULNESS = 0.9
MIN_RUBRIC = 3
EXPORT_DIR = REPO_ROOT / "data" / "exports"


class PlannedLesson(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    objectives: list[str] = Field(min_length=1, max_length=3)
    section: str


class CoursePlan(BaseModel):
    title: str
    description: str
    lessons: list[PlannedLesson] = Field(min_length=2, max_length=MAX_LESSONS)


def plan_problems(plan: CoursePlan, sections: list[str], wanted: int) -> list[str]:
    problems = []
    if len(plan.lessons) != wanted:
        problems.append(f"the plan has {len(plan.lessons)} lessons, {wanted} were asked for")
    if unknown := [lesson.section for lesson in plan.lessons if lesson.section not in sections]:
        problems.append(f"these sections aren't in the list: {unknown}")
    if len({lesson.topic.lower() for lesson in plan.lessons}) < len(plan.lessons):
        problems.append("two lessons have the same topic")
    return problems


def meets_bar(outcome: dict) -> bool:
    return outcome["faithfulness"] >= MIN_FAITHFULNESS and min(outcome["rubric"].values()) >= MIN_RUBRIC


def over_limits(spent: float, started: float) -> str | None:
    if spent >= BUDGET_USD:
        return f"spending cap reached (${spent:.3f} of ${BUDGET_USD:.2f})"
    if time.monotonic() - started >= TIME_LIMIT_S:
        return f"time cap reached ({TIME_LIMIT_S // 60} min)"
    return None


async def run_course(goal: str, wanted: int, approve: Callable[[str], bool]) -> str:
    check_text(goal)
    started, spent = time.monotonic(), 0.0
    async with await connect() as conn:
        rows = await (await conn.execute("SELECT DISTINCT section_path FROM chunks ORDER BY 1")).fetchall()
        sections = [row["section_path"] for row in rows]

        system, _ = load_prompt("planner")
        prompt = f"Goal: {goal}\nLessons wanted: {wanted}\nSections of the book:\n" + "\n".join(sections)
        plan, result, _ = await asyncio.to_thread(
            generate, CoursePlan, system, prompt, lambda p: plan_problems(p, sections, wanted)
        )
        spent += result.cost_usd

        print(f"\n{plan.title}: {plan.description}")
        for i, lesson in enumerate(plan.lessons, 1):
            print(f"  {i}. {lesson.topic}  [{lesson.section}]")
            for objective in lesson.objectives:
                print(f"     - {objective}")
        if not approve(f"Generate these {len(plan.lessons)} lessons?"):
            return "stopped: plan not approved"

        outcomes = []
        for planned in plan.lessons:
            if reason := over_limits(spent, started):
                print(f"  stopping early: {reason}")
                break
            request = LessonRequest(topic=planned.topic, objectives=planned.objectives)
            try:
                lesson = await create_lesson(conn, request)
                review, judged = await asyncio.to_thread(review_lesson, lesson)
            except (Blocked, GenerationError, LLMError) as e:
                print(f"  x {planned.topic}: {e}")
                continue
            cur = await conn.execute(
                "SELECT sum(cost_usd)::float AS cost FROM runs WHERE lesson_id = %s", [lesson["id"]]
            )
            spent += (await cur.fetchone())["cost"] + judged.cost_usd
            claims = review.claims
            outcome = {
                "lesson": lesson,
                "faithfulness": sum(c.supported for c in claims) / len(claims) if claims else 0.0,
                "rubric": {name: getattr(review, name).score for name in CRITERIA},
            }
            outcomes.append(outcome)
            flag = "ok" if meets_bar(outcome) else "below the bar"
            lowest = min(outcome["rubric"].values())
            print(
                f"  {lesson['id']:>4} {lesson['lesson']['title'][:60]:<60} "
                f"faithfulness {outcome['faithfulness']:.2f}, lowest rubric {lowest}: {flag}"
            )

        print(f"  estimated cost so far: ${spent:.4f}")
        keep = [o["lesson"] for o in outcomes if meets_bar(o)]
        if not keep:
            return "stopped: no lesson met the quality bar"
        if not approve(f"Export {len(keep)} lesson(s) as a cmi5 course?"):
            return "stopped: export not approved"

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / f"course-{'-'.join(str(lesson['id']) for lesson in keep)}-cmi5.zip"
    path.write_bytes(build_cmi5_course(plan.title, plan.description, keep, MEDIA_DIR))
    return f"exported {path}"


def ask(question: str) -> bool:
    return input(f"\n{question} [y/N] ").strip().lower() in ("y", "yes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan, write, review and export a short course.")
    parser.add_argument("goal")
    parser.add_argument("--lessons", type=int, default=3, choices=range(2, MAX_LESSONS + 1))
    parser.add_argument("--yes", action="store_true", help="approve the plan and the export without asking")
    args = parser.parse_args()
    try:
        print(run(run_course(args.goal, args.lessons, (lambda q: True) if args.yes else ask)))
    except Blocked as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
