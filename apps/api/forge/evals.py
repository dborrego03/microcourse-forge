"""Offline evaluations.

    uv run python -m forge.evals retrieval [--mode vector] [--check]

Results go to evals/results/ and to the eval_runs table, so every number in
the README can be traced back to a commit.
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from psycopg.types.json import Jsonb

from forge.db import connect, run
from forge.search import SEARCH_MODES

EVALS_DIR = Path(__file__).resolve().parents[3] / "evals"


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "describe", "--always", "--dirty", "--abbrev=7"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


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


def percentile(values: list[float], p: int) -> float:
    return round(statistics.quantiles(values, n=100)[p - 1], 1)


async def eval_retrieval(mode: str, dataset: str = "retrieval_v1") -> dict:
    cases = load_cases(dataset)
    search = SEARCH_MODES[mode]

    async with await connect() as conn:
        rows = await (await conn.execute("SELECT text FROM chunks")).fetchall()
        corpus = [normalize(row["text"]) for row in rows]
        missing = [c["id"] for c in cases if normalize(c["evidence"]) not in " ".join(corpus)]
        if missing:
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
        await conn.execute(
            "INSERT INTO eval_runs (kind, dataset, config, metrics, git_sha) VALUES (%s, %s, %s, %s, %s)",
            ["retrieval", dataset, Jsonb(report["config"]), Jsonb(metrics), report["git_sha"]],
        )
        await conn.commit()
    return report


def check(report: dict) -> list[str]:
    config = tomllib.loads((EVALS_DIR / "thresholds.toml").read_text())
    thresholds = config[report["kind"]].get(report["config"]["mode"])
    if thresholds is None:
        return [f"no thresholds for {report['kind']}.{report['config']['mode']} in thresholds.toml"]
    return [
        f"{name} = {report['metrics'][name]} is below {minimum}"
        for name, minimum in thresholds.items()
        if report["metrics"][name] < minimum
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["retrieval"])
    parser.add_argument("--mode", choices=list(SEARCH_MODES), default="vector")
    parser.add_argument("--check", action="store_true", help="exit 1 if a metric is below its threshold")
    args = parser.parse_args()

    report = run(eval_retrieval(args.mode))
    out = EVALS_DIR / "results" / f"retrieval-{args.mode}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")

    print(
        f"{report['kind']} ({args.mode}) on {report['dataset']}, {report['cases']} cases, {report['git_sha']}"
    )
    for name, value in report["metrics"].items():
        print(f"  {name:<16} {value}")
    if report["misses"]:
        print(f"  not found in top 10: {', '.join(report['misses'])}")

    if args.check and (failures := check(report)):
        sys.exit("quality gate failed:\n  " + "\n  ".join(failures))


if __name__ == "__main__":
    main()
