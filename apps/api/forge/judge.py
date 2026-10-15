"""LLM judge for generated lessons: faithfulness, relevance and the pedagogical rubric.

The judge is a different model from the generator so it isn't grading its own
writing. Its scores still need checking against human labels (see evals/README.md).
"""

import json
import os

from pydantic import BaseModel, Field

from forge.lessons import load_prompt
from forge.llm import LLMResult, complete_json

JUDGE_MODEL = os.environ.get("FORGE_JUDGE_MODEL", "claude-sonnet-5-5")
CRITERIA = ("alignment", "accuracy", "clarity", "examples", "assessment", "structure")


class Claim(BaseModel):
    claim: str
    supported: bool


class SectionReview(BaseModel):
    section: int = Field(ge=1)
    claims: list[Claim]


class Score(BaseModel):
    score: int = Field(ge=1, le=5)
    reason: str


class Review(BaseModel):
    sections: list[SectionReview]
    relevance: Score
    alignment: Score
    accuracy: Score
    clarity: Score
    examples: Score
    assessment: Score
    structure: Score

    @property
    def claims(self) -> list[Claim]:
        return [c for s in self.sections for c in s.claims]


def review_lesson(lesson: dict) -> tuple[Review, LLMResult]:
    """`lesson` is a row from forge.lessons.get_lesson."""
    system, _ = load_prompt("judge")
    sources = "\n".join(
        f'<source id="{s["id"]}" section="{s["section"]}">\n{s["text"]}\n</source>' for s in lesson["sources"]
    )
    prompt = (
        f"Request:\n{json.dumps(lesson['request'], indent=1)}\n\n"
        f"Lesson:\n{json.dumps(lesson['lesson'], indent=1)}\n\n"
        f"Quiz:\n{json.dumps(lesson['quiz'], indent=1)}\n\n"
        f"<sources>\n{sources}\n</sources>"
    )
    result = complete_json(system, prompt, Review, JUDGE_MODEL)
    return Review.model_validate(result.data), result
