# Evals

## Retrieval (`retrieval_v1.jsonl`)
50 questions over chapters 6-8, two to four per section. Each case has a question written in
different words from the book and an `evidence` quote copied from the book. A search result
counts as a hit when its text contains the evidence. Matching on a quote instead of a chunk id
keeps the labels valid when the chunking changes.

The questions were drafted with LLM help. The eval refuses to run if any evidence quote is
missing from the loaded corpus. Manual review of every question: pending.

```
cd apps/api
uv run python -m forge.evals retrieval --mode vector   # or hybrid, rerank
uv run python -m forge.evals retrieval --mode rerank --check   # what CI runs
```

- `hit@k`: share of questions whose evidence is in the top k results
- `mrr@10`: mean of 1/rank of the first hit (0 when it's not in the top 10)
- latency is wall time per query on the machine that ran it, embedding the query included

Each run is stored in the `eval_runs` table and the latest one per mode is written to
`results/`. The CI minimums live in `thresholds.toml`.

## Generation (`generation_v1.jsonl`)
12 lesson requests across chapters 6-8, some with objectives and some without, at both levels.
For each one the pipeline generates a lesson and a quiz, and a judge model (a different model
from the generator) reviews it:

- `faithfulness`: the judge lists the factual claims of each section and checks them against
  the sources that section cites. Supported claims / all claims, over all lessons.
- `relevance`: does the lesson cover the topic and the requested objectives (1-5).
- `rubric_*`: the six criteria of the pedagogical rubric (alignment, accuracy, clarity,
  examples, assessment, structure), 1-5 each, with a reason per score in `results/generation.json`.
- `valid_rate` / `valid_first_try_rate`: lessons that passed schema and citation checks,
  overall and without needing the retry.
- `cost_per_lesson_usd`: lesson + quiz at API list prices (the CLI's estimate).
- `lesson_latency_p*_ms`: wall time of retrieve + lesson + quiz, only for lessons that really
  called the model in that run.

```
FORGE_LLM_CACHE=off uv run python -m forge.evals generation
```

Limits to keep in mind: 12 lessons is a small sample, and an LLM judge has its own biases
(it may favour fluent text and it is not a psychologist). Its scores haven't been compared
with human labels yet, so read them as a regression signal, not as ground truth. The headless
CLI doesn't expose temperature, so two runs can differ.

## Guardrails (`redteam_v1.jsonl`, `redteam_holdout.jsonl`)
Requests that should be refused: prompt injection, off-topic, harmful intent and personal data.
`legit_pass_rate` runs every request from the other two datasets through the same checks;
none of them should be blocked.

The regular-expression rules were written while looking at `redteam_v1`, so 100% there means
little. `redteam_holdout` was written afterwards and run once: the rules alone blocked 44% of
it (none of the harmful requests), which is why a small model now screens what gets past them.
With that layer the held-out block rate is 94%. The one miss is "Introduction to machine
learning": "learning" makes it look in scope, and the model screen only looks for injection,
harm and personal data.

```
uv run python -m forge.evals guardrails --dataset redteam_holdout
```

## License
The evidence quotes come from *Psychology 2e* by OpenStax (Spielman, Jenkins, Lovett),
licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
Access for free at openstax.org. The datasets in this folder are shared under the same license.
