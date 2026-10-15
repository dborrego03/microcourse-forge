"""Input guardrails: checks that run before any model call.

Cheap checks go first: regular expressions and a relevance threshold. The rules
were written against evals/redteam_v1.jsonl and caught under half of a held-out
set, so a small model screens whatever gets past them (moderate).

Other layers: retrieved text is wrapped as untrusted data (lessons.format_sources),
output must validate and cite provided sources (lessons.generate), and
faithfulness is checked offline by the judge.
"""

import json
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from forge.llm import complete_json

# Top re-ranker score (jina-reranker-v1-tiny-en logit) below which a request is
# treated as outside the book. Off-topic red-team inputs scored -0.87 or lower and
# 61 of 62 in-scope requests scored -0.29 or higher, so -0.6 sits in the gap.
SCOPE_MIN_SCORE = -0.6

RULES = {
    "injection": re.compile(
        r"\b(ignore|disregard|forget|override)\b[^.]{0,40}\b(instructions?|rules|guidelines|prompt)\b"
        r"|system prompt|hidden instructions|developer mode|jailbreak|\byou are now\b|\bact as\b"
        r"|\bpretend\b|</?\s*source",
        re.IGNORECASE,
    ),
    "harmful": re.compile(
        r"\b(how|ways?|techniques?|steps|tips)\s+to\s+"
        r"(abuse|hurt|harm|kill|stalk|manipulate|cheat|poison|attack|groom|make a (weapon|bomb))\b",
        re.IGNORECASE,
    ),
    "personal_data": re.compile(
        r"[\w.+-]+@[\w-]+\.\w+"  # email
        r"|\+?\d[\d\s-]{7,}\d"  # phone number
        r"|\bmy (patient|client|coworker|colleague|son|daughter|child|wife|husband|partner|friend|boss)\b",
        re.IGNORECASE,
    ),
}

MESSAGES = {
    "injection": "The request looks like an attempt to change the assistant's instructions.",
    "harmful": "The request asks for help with something harmful.",
    "personal_data": "Please don't include personal data about real people.",
    "off_topic": "That topic isn't covered by the source book (chapters on learning, thinking and memory).",
}


GUARD_MODEL = os.environ.get("FORGE_GUARD_MODEL", "claude-haiku-5-5")
GUARD_PROMPT = (Path(__file__).parent / "prompts" / "guard.md").read_text(encoding="utf-8")


class Verdict(BaseModel):
    refuse: bool
    category: Literal["injection", "harmful", "personal_data", "none"]
    reason: str


class Blocked(Exception):
    def __init__(self, rule: str):
        self.rule = rule
        super().__init__(MESSAGES[rule])


def check_text(*texts: str) -> None:
    for rule, pattern in RULES.items():
        if any(pattern.search(text) for text in texts):
            raise Blocked(rule)


def check_scope(top_score: float) -> None:
    if top_score < SCOPE_MIN_SCORE:
        raise Blocked("off_topic")


def moderate(topic: str, objectives: list[str]) -> None:
    request = json.dumps({"topic": topic, "objectives": objectives})
    result = complete_json(GUARD_PROMPT, f"Request:\n{request}", Verdict.model_json_schema(), GUARD_MODEL)
    verdict = Verdict.model_validate(result.data)
    if verdict.refuse and verdict.category != "none":
        raise Blocked(verdict.category)
