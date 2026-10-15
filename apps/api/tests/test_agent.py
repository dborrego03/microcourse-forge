from types import SimpleNamespace

from forge import agent
from forge.agent import CoursePlan, PlannedLesson, meets_bar, plan_problems, run_course
from forge.judge import Claim, Review, Score, SectionReview
from forge.llm import LLMResult

SECTIONS = ["8 Memory > 8.1 How Memory Functions", "8 Memory > 8.3 Problems with Memory"]


def planned(topic, section=SECTIONS[0]):
    return PlannedLesson(topic=topic, objectives=["Explain it"], section=section)


def test_plan_problems():
    good = CoursePlan(
        title="T", description="D", lessons=[planned("Encoding"), planned("Forgetting", SECTIONS[1])]
    )
    assert plan_problems(good, SECTIONS, 2) == []

    bad = CoursePlan(
        title="T", description="D", lessons=[planned("Encoding"), planned("encoding", "9 Lifespan")]
    )
    problems = plan_problems(bad, SECTIONS, 3)
    assert "the plan has 2 lessons, 3 were asked for" in problems
    assert "these sections aren't in the list: ['9 Lifespan']" in problems
    assert "two lessons have the same topic" in problems


def test_quality_bar():
    rubric = {"alignment": 4, "accuracy": 4, "clarity": 3}
    assert meets_bar({"faithfulness": 0.95, "rubric": rubric})
    assert not meets_bar({"faithfulness": 0.85, "rubric": rubric})
    assert not meets_bar({"faithfulness": 1.0, "rubric": {**rubric, "clarity": 2}})


class FakeConn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        rows = (
            [{"section_path": s} for s in SECTIONS] if "section_path" in sql else [{"cost": 0.01, "t": None}]
        )

        async def fetchall():
            return rows

        async def fetchone():
            return rows[0]

        return SimpleNamespace(fetchall=fetchall, fetchone=fetchone)


def review(supported: list[bool], score=4) -> Review:
    claims = [Claim(claim=f"c{i}", supported=s) for i, s in enumerate(supported)]
    scores = {name: Score(score=score, reason="r") for name in agent.CRITERIA}
    return Review(
        sections=[SectionReview(section=1, claims=claims)], relevance=Score(score=5, reason="r"), **scores
    )


def wire(monkeypatch, tmp_path, reviews):
    plan = CoursePlan(
        title="Memory", description="D", lessons=[planned("Encoding"), planned("Forgetting", SECTIONS[1])]
    )
    created = []

    async def fake_connect():
        return FakeConn()

    async def fake_create(conn, request):
        created.append(request.topic)
        return {"id": len(created), "lesson": {"title": request.topic, "summary": "s"}}

    monkeypatch.setattr(agent, "connect", fake_connect)
    monkeypatch.setattr(agent, "generate", lambda *a: (plan, LLMResult({}, "m", 1, 1, 0.001, 1), 0))
    monkeypatch.setattr(agent, "create_lesson", fake_create)
    monkeypatch.setattr(
        agent, "review_lesson", lambda lesson: (reviews[lesson["id"] - 1], LLMResult({}, "m", 1, 1, 0.02, 1))
    )
    monkeypatch.setattr(
        agent,
        "build_cmi5_course",
        lambda title, desc, lessons, root: str([lesson["id"] for lesson in lessons]).encode(),
    )
    monkeypatch.setattr(agent, "EXPORT_DIR", tmp_path)
    return created


async def test_nothing_is_generated_without_approving_the_plan(monkeypatch, tmp_path):
    created = wire(monkeypatch, tmp_path, [review([True])] * 2)
    assert await run_course("memory", 2, approve=lambda q: False) == "stopped: plan not approved"
    assert created == []


async def test_only_lessons_that_meet_the_bar_are_exported(monkeypatch, tmp_path):
    wire(monkeypatch, tmp_path, [review([True, True]), review([True, False])])  # second: faithfulness 0.5
    result = await run_course("memory", 2, approve=lambda q: True)
    assert result.endswith("course-1-cmi5.zip")
    assert (tmp_path / "course-1-cmi5.zip").read_bytes() == b"[1]"


async def test_the_spending_cap_stops_the_loop(monkeypatch, tmp_path):
    created = wire(monkeypatch, tmp_path, [review([True])] * 2)
    monkeypatch.setattr(agent, "BUDGET_USD", 0.02)  # the first lesson plus its review costs 0.03
    await run_course("memory", 2, approve=lambda q: True)
    assert created == ["Encoding"]
