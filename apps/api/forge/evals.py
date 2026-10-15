"""Offline evaluations.

    uv run python -m forge.evals retrieval [--mode vector|hybrid|rerank] [--check]
    uv run python -m forge.evals generation [--check]
    uv run python -m forge.evals guardrails [--check]

Results go to evals/results/ and to the eval_runs table, so every number in
the README can be traced back to a commit.
"""

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
import tomllib
from pathlib import Path

from psycopg.types.json import Jsonb

from forge.db import connect, run
from forge.guardrails import Blocked, check_scope, check_text, moderate
from forge.judge import CRITERIA, JUDGE_MODEL, review_lesson
from forge.lessons import GENERATOR_MODEL, GenerationError, LessonRequest, create_lesson, load_prompt
from forge.llm import LLMError
from forge.search import SEARCH_MODES, rerank_search
from forge.version import git_sha

EVALS_DIR = Path(__file__).resolve().parents[3] / "evals"


def normalize(text: str) -> str:
    text = text.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
    return re.sub(r"\s+", " ", text).strip().lower()


def load_cases(name: str) -> list[dict]:
    lines = (EVALS_DIR / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def first_hit(results: list[dict], evidence: str) -> int | None:
    """1-based rank of the first result that contains the evidence, or None."""
    evidence = normalize(evidence)
    return next((i for i, r in enumerate(results, 1) if evidence in normalize(r["text"])), None)


def retrieval_metrics(ranks: list[int | None], ks=(1, 3, 5, 10)) -> dict:
    metrics = {f"hit@{k}": sum(1 for r in ranks if r and r <= k) / len(ranks) for k in ks}
    metrics["mrr@10"] = sum(1 / r for r in ranks if r and r <= 10) / len(ranks)
    return {name: round(value, 3) for name, value in metrics.items()}


def percentile(values: list[float], p: int) -> float | None:
    if len(values) < 2:
        return round(values[0], 1) if values else None
    return round(statistics.quantiles(values, n=100)[p - 1], 1)


async def save(conn, report: dict) -> None:
    await conn.execute(
        "INSERT INTO eval_runs (kind, dataset, config, metrics, git_sha) VALUES (%s, %s, %s, %s, %s)",
        [
            report["kind"],
            report["dataset"],
            Jsonb(report["config"]),
            Jsonb(report["metrics"]),
            report["git_sha"],
        ],
    )
    await conn.commit()


async def eval_retrieval(mode: str, dataset: str = "retrieval_v1") -> dict:
    cases = load_cases(dataset)
    search = SEARCH_MODES[mode]

    async with await connect() as conn:
        rows = await (await conn.execute("SELECT text FROM chunks")).fetchall()
        corpus = " ".join(normalize(row["text"]) for row in rows)
        if missing := [c["id"] for c in cases if normalize(c["evidence"]) not in corpus]:
            sys.exit(f"evidence not found in the loaded corpus for: {', '.join(missing)}")

        ranks, latencies = [], []
        for case in cases:
            started = time.perf_counter()
            results = await search(conn, case["question"], 10)
            latencies.append((time.perf_counter() - started) * 1000)
            ranks.append(first_hit(results, case["evidence"]))

        metrics = retrieval_metrics(ranks)
        metrics["latency_p50_ms"] = percentile(latencies, 50)
        metrics["latency_p95_ms"] = percentile(latencies, 95)
        report = {
            "kind": "retrieval",
            "dataset": dataset,
            "cases": len(cases),
            "config": {"mode": mode},
            "metrics": metrics,
            "misses": [c["id"] for c, r in zip(cases, ranks, strict=True) if r is None],
            "git_sha": git_sha(),
        }
        await save(conn, report)
    return report


def generation_metrics(rows: list[dict]) -> dict:
    ready = [r for r in rows if r["status"] == "ready"]
    claims = sum(r["claims"] for r in ready)
    fresh = [r for r in ready if not r["cached"]]
    metrics = {
        "valid_rate": len(ready) / len(rows),
        "valid_first_try_rate": sum(1 for r in ready if r["retries"] == 0) / len(rows),
        "faithfulness": sum(r["supported"] for r in ready) / claims if claims else 0.0,
        "relevance": statistics.mean(r["relevance"] for r in ready) if ready else 0.0,
    }
    for name in CRITERIA:
        metrics[f"rubric_{name}"] = statistics.mean(r["rubric"][name] for r in ready) if ready else 0.0
    metrics["rubric_mean"] = statistics.mean(metrics[f"rubric_{n}"] for n in CRITERIA)
    metrics = {name: round(value, 3) for name, value in metrics.items()}
    # Cost is the API-price estimate of the original calls, so it holds for cached rows too.
    metrics["cost_per_lesson_usd"] = (
        round(statistics.mean(r["cost_usd"] for r in ready), 4) if ready else None
    )
    # Latency only makes sense for lessons that really called the model in this run.
    metrics["lesson_latency_p50_ms"] = percentile([r["latency_ms"] for r in fresh], 50)
    metrics["lesson_latency_p95_ms"] = percentile([r["latency_ms"] for r in fresh], 95)
    metrics["fresh_lessons"] = len(fresh)
    return metrics


async def eval_generation(dataset: str = "generation_v1") -> dict:
    cases = load_cases(dataset)
    rows = []
    async with await connect() as conn:
        for case in cases:
            request = LessonRequest(topic=case["topic"], objectives=case["objectives"], level=case["level"])
            print(f"  {case['id']} {case['topic']}", file=sys.stderr, flush=True)
            try:
                lesson = await create_lesson(conn, request)
                review, _ = await asyncio.to_thread(review_lesson, lesson)
            except (GenerationError, LLMError) as e:
                rows.append({"id": case["id"], "status": "failed", "error": str(e)[:300]})
                continue
            cur = await conn.execute(
                """SELECT sum(retries) AS retries, sum(cost_usd)::float AS cost, sum(latency_ms) AS latency,
                          bool_or(cached) AS cached
                   FROM runs WHERE lesson_id = %s""",
                [lesson["id"]],
            )
            stats = await cur.fetchone()
            rows.append(
                {
                    "id": case["id"],
                    "lesson_id": lesson["id"],
                    "status": "ready",
                    "retries": stats["retries"],
                    "cached": stats["cached"],
                    "cost_usd": stats["cost"],
                    "latency_ms": stats["latency"],
                    "claims": len(review.claims),
                    "supported": sum(c.supported for c in review.claims),
                    "unsupported": [c.claim for c in review.claims if not c.supported],
                    "relevance": review.relevance.score,
                    "rubric": {name: getattr(review, name).score for name in CRITERIA},
                    "reasons": {name: getattr(review, name).reason for name in ("relevance", *CRITERIA)},
                }
            )

        report = {
            "kind": "generation",
            "dataset": dataset,
            "cases": len(cases),
            "config": {
                "generator": GENERATOR_MODEL,
                "judge": JUDGE_MODEL,
                "prompts": {name: load_prompt(name)[1] for name in ("lesson", "quiz", "judge")},
            },
            "metrics": generation_metrics(rows),
            "git_sha": git_sha(),
            "lessons": rows,
        }
        await save(conn, report)
    return report


async def blocked_by(conn, topic: str, objectives: list[str]) -> str | None:
    try:
        check_text(topic, *objectives)
        results = await rerank_search(conn, " ".join([topic, *objectives]), 1)
        check_scope(results[0]["score"])
        await asyncio.to_thread(moderate, topic, objectives)
    except Blocked as e:
        return e.rule
    return None


async def eval_guardrails(dataset: str = "redteam_v1") -> dict:
    attacks = load_cases(dataset)
    # Everything in the other datasets is a legitimate request that must get through.
    legit = [(c["question"], []) for c in load_cases("retrieval_v1")]
    legit += [(c["topic"], c["objectives"]) for c in load_cases("generation_v1")]

    async with await connect() as conn:
        results = [(c, await blocked_by(conn, c["topic"], c["objectives"])) for c in attacks]
        false_positives = [topic for topic, objectives in legit if await blocked_by(conn, topic, objectives)]

        metrics = {"block_rate": sum(1 for _, rule in results if rule) / len(results)}
        for kind in sorted({c["kind"] for c in attacks}):
            of_kind = [rule for c, rule in results if c["kind"] == kind]
            metrics[f"block_rate_{kind}"] = sum(1 for rule in of_kind if rule) / len(of_kind)
        metrics["legit_pass_rate"] = 1 - len(false_positives) / len(legit)
        report = {
            "kind": "guardrails",
            "dataset": dataset,
            "cases": len(attacks),
            "config": {"legit_cases": len(legit)},
            "metrics": {name: round(value, 3) for name, value in metrics.items()},
            "missed": [c["id"] for c, rule in results if not rule],
            "false_positives": false_positives,
            "git_sha": git_sha(),
        }
        await save(conn, report)
    return report


def check(report: dict) -> list[str]:
    config = tomllib.loads((EVALS_DIR / "thresholds.toml").read_text())
    thresholds = config.get(report["kind"], {})
    if mode := report["config"].get("mode"):
        thresholds = thresholds.get(mode, {})
    if not thresholds:
        return [f"no thresholds for {report['kind']} {mode or ''} in thresholds.toml"]
    return [
        f"{name} = {report['metrics'][name]} is below {minimum}"
        for name, minimum in thresholds.items()
        if report["metrics"][name] < minimum
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["retrieval", "generation", "guardrails"])
    parser.add_argument("--mode", choices=list(SEARCH_MODES), default="vector", help="retrieval only")
    parser.add_argument("--dataset", default="redteam_v1", help="guardrails only")
    parser.add_argument("--check", action="store_true", help="exit 1 if a metric is below its threshold")
    args = parser.parse_args()

    if args.kind == "retrieval":
        report = run(eval_retrieval(args.mode))
        name = f"retrieval-{args.mode}"
    elif args.kind == "generation":
        report = run(eval_generation())
        name = "generation"
    else:
        report = run(eval_guardrails(args.dataset))
        name = f"guardrails-{args.dataset}"
    out = EVALS_DIR / "results" / f"{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"{name} on {report['dataset']}, {report['cases']} cases, {report['git_sha']}")
    for metric, value in report["metrics"].items():
        print(f"  {metric:<24} {value}")
    if report.get("misses"):
        print(f"  not found in top 10: {', '.join(report['misses'])}")
    if report.get("missed"):
        print(f"  attacks that got through: {', '.join(report['missed'])}")
    for text in report.get("false_positives", []):
        print(f"  legit request blocked: {text}")

    if args.check and (failures := check(report)):
        sys.exit("quality gate failed:\n  " + "\n  ".join(failures))


if __name__ == "__main__":
    main()
