"""Check the LLM judge against human labels.

    uv run python -m forge.calibration export      # writes evals/labels.csv to fill in by hand
    uv run python -m forge.calibration agreement   # compares the filled-in scores with the judge

Fill in the 1-5 rubric scores in labels.csv after reading each lesson in the web app,
without looking at the judge's scores first. Rows left blank are skipped.
"""

import argparse
import asyncio
import csv
import json
import sys
from itertools import product

from forge.db import connect, run
from forge.evals import EVALS_DIR, save
from forge.judge import CRITERIA, JUDGE_MODEL, review_lesson
from forge.lessons import get_lesson
from forge.version import git_sha

LABELS = EVALS_DIR / "labels.csv"
WEB_URL = "http://localhost:3000"
SAMPLE = 30


def weighted_kappa(a: list[int], b: list[int], categories=range(1, 6)) -> float:
    """Cohen's kappa with quadratic weights: disagreeing by 2 points costs four times more than by 1."""
    cats = list(categories)
    n, k = len(a), len(cats)
    observed = {(i, j): 0 for i, j in product(cats, cats)}
    for x, y in zip(a, b, strict=True):
        observed[x, y] += 1
    weight = {(i, j): ((i - j) / (k - 1)) ** 2 for i, j in product(cats, cats)}
    expected = {(i, j): a.count(i) * b.count(j) / n for i, j in product(cats, cats)}
    disagreement_expected = sum(weight[c] * expected[c] for c in weight)
    if disagreement_expected == 0:
        return 1.0  # both raters used one single score
    return 1 - sum(weight[c] * observed[c] for c in weight) / disagreement_expected


def agreement_metrics(human: list[int], judge: list[int]) -> dict:
    pairs = list(zip(human, judge, strict=True))
    return {
        "exact": round(sum(h == j for h, j in pairs) / len(pairs), 3),
        "within_1": round(sum(abs(h - j) <= 1 for h, j in pairs) / len(pairs), 3),
        "weighted_kappa": round(weighted_kappa(human, judge), 3),
        "mean_difference": round(sum(j - h for h, j in pairs) / len(pairs), 3),  # > 0: judge is more generous
    }


async def export() -> None:
    if LABELS.exists():
        sys.exit(f"{LABELS} already exists; delete it first if you want a new sample")
    async with await connect() as conn:
        cur = await conn.execute(
            # Repeated requests (tests, cache hits) give identical lessons; keep one of each.
            """SELECT * FROM (
                   SELECT DISTINCT ON (lesson->>'title') id, lesson->>'title' AS title FROM lessons
                   WHERE status = 'ready' ORDER BY lesson->>'title', id DESC
               ) latest ORDER BY id DESC LIMIT %s""",
            [SAMPLE],
        )
        rows = await cur.fetchall()
    with LABELS.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["lesson_id", "title", "url", *CRITERIA, "notes"])
        for row in rows:
            writer.writerow(
                [row["id"], row["title"], f"{WEB_URL}/lessons/{row['id']}", *[""] * len(CRITERIA), ""]
            )
    print(f"wrote {len(rows)} lessons to {LABELS}")


async def agreement() -> dict:
    with LABELS.open(encoding="utf-8") as f:
        labelled = [r for r in csv.DictReader(f) if all(r[c].strip() for c in CRITERIA)]
    if not labelled:
        sys.exit(f"no fully labelled rows in {LABELS} yet")

    human = {c: [] for c in CRITERIA}
    judge = {c: [] for c in CRITERIA}
    async with await connect() as conn:
        for row in labelled:
            lesson = await get_lesson(conn, int(row["lesson_id"]))
            review, _ = await asyncio.to_thread(review_lesson, lesson)  # cached if judged before
            for c in CRITERIA:
                human[c].append(int(row[c]))
                judge[c].append(getattr(review, c).score)

        metrics = {c: agreement_metrics(human[c], judge[c]) for c in CRITERIA}
        report = {
            "kind": "judge_agreement",
            "dataset": "labels",
            "cases": len(labelled),
            "config": {"judge": JUDGE_MODEL},
            "metrics": {f"{c}_{name}": v for c, m in metrics.items() for name, v in m.items()},
            "git_sha": git_sha(),
        }
        await save(conn, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["export", "agreement"])
    args = parser.parse_args()
    if args.command == "export":
        run(export())
        return
    report = run(agreement())
    (EVALS_DIR / "results" / "judge-agreement.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"judge vs. human on {report['cases']} lessons")
    print(f"  {'criterion':<12} {'exact':>6} {'within 1':>9} {'kappa':>6} {'judge - human':>14}")
    for c in CRITERIA:
        m = {name: report["metrics"][f"{c}_{name}"] for name in ("exact", "within_1", "weighted_kappa")}
        diff = report["metrics"][f"{c}_mean_difference"]
        print(f"  {c:<12} {m['exact']:>6} {m['within_1']:>9} {m['weighted_kappa']:>6} {diff:>14}")


if __name__ == "__main__":
    main()
