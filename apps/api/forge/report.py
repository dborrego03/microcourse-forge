"""Build the README's metrics tables from the committed eval results.

    uv run python -m forge.report            # print the tables
    uv run python -m forge.report --write    # replace the block in README.md
    uv run python -m forge.report --check    # exit 1 if README.md is out of date (CI)

The numbers are never typed by hand: they come from evals/results/*.json, and each
table says which command produced them.
"""

import argparse
import json
import sys

from forge import REPO_ROOT
from forge.evals import EVALS_DIR

README = REPO_ROOT / "README.md"
START, END = "<!-- metrics:start -->", "<!-- metrics:end -->"


def load(name: str) -> dict | None:
    path = EVALS_DIR / "results" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def seconds(ms: float | None) -> str:
    return "–" if ms is None else f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms:.0f} ms"


def table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines)


def render() -> str:
    parts = []

    retrieval = [r for mode in ("vector", "hybrid", "rerank") if (r := load(f"retrieval-{mode}"))]
    if retrieval:
        first = retrieval[0]
        parts.append(
            f"**Retrieval** · {first['dataset']}, {first['cases']} questions · "
            "`uv run python -m forge.evals retrieval --mode <mode>`\n\n"
            + table(
                ["Mode", "hit@1", "hit@5", "MRR@10", "p50 latency", "Commit"],
                [
                    [
                        r["config"]["mode"],
                        m["hit@1"],
                        m["hit@5"],
                        m["mrr@10"],
                        seconds(m["latency_p50_ms"]),
                        r["git_sha"],
                    ]
                    for r in retrieval
                    for m in [r["metrics"]]
                ],
            )  # fmt: skip
        )

    if g := load("generation"):
        m = g["metrics"]
        parts.append(
            f"**Generation** · {g['dataset']}, {g['cases']} lessons · generator {g['config']['generator']}, "
            f"judge {g['config']['judge']} · commit {g['git_sha']} · "
            "`FORGE_LLM_CACHE=off uv run python -m forge.evals generation`\n\n"
            + table(
                ["Metric", "Value"],
                [
                    ["Valid JSON on the first try", m["valid_first_try_rate"]],
                    ["Faithfulness (claims backed by the cited sources)", m["faithfulness"]],
                    ["Relevance (1-5)", m["relevance"]],
                    ["Pedagogical rubric, mean of 6 criteria (1-5)", m["rubric_mean"]],
                    ["Estimated cost per lesson (API list prices)", f"${m['cost_per_lesson_usd']}"],
                    [
                        "Latency per lesson, p50 / p95",
                        f"{seconds(m['lesson_latency_p50_ms'])} / {seconds(m['lesson_latency_p95_ms'])}",
                    ],
                ],
            )  # fmt: skip
        )

    guardrails = [r for name in ("redteam_v1", "redteam_holdout") if (r := load(f"guardrails-{name}"))]
    if guardrails:
        parts.append(
            "**Guardrails** · `uv run python -m forge.evals guardrails --dataset <dataset>`\n\n"
            + table(
                ["Attack set", "Attacks", "Blocked", "Legitimate requests let through", "Commit"],
                [
                    [
                        r["dataset"],
                        r["cases"],
                        r["metrics"]["block_rate"],
                        r["metrics"]["legit_pass_rate"],
                        r["git_sha"],
                    ]
                    for r in guardrails
                ],
            )  # fmt: skip
            + "\n\nThe rules were written while looking at redteam_v1; "
            "the holdout set was written afterwards."
        )

    if j := load("judge-agreement"):
        m = j["metrics"]
        criteria = sorted({k.rsplit("_", 2)[0] for k in m if k.endswith("weighted_kappa")})
        parts.append(
            f"**Judge vs. human labels** · {j['cases']} lessons · "
            "`uv run python -m forge.calibration agreement`\n\n"
            + table(
                ["Criterion", "Exact", "Within 1", "Weighted kappa"],
                [[c, m[f"{c}_exact"], m[f"{c}_within_1"], m[f"{c}_weighted_kappa"]] for c in criteria],
            )
        )
    else:
        parts.append("**Judge vs. human labels** · not labelled yet (see `evals/README.md`).")

    return "\n\n".join(parts)


def with_block(readme: str, block: str) -> str:
    before, rest = readme.split(START, 1)
    _, after = rest.split(END, 1)
    return f"{before}{START}\n{block}\n{END}{after}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    block = render()
    if not (args.write or args.check):
        print(block)
        return
    readme = README.read_text(encoding="utf-8")
    updated = with_block(readme, block)
    if args.check:
        if updated != readme:
            sys.exit("README.md metrics are out of date: run `uv run python -m forge.report --write`")
        return
    README.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
