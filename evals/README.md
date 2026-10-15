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

## License
The evidence quotes come from *Psychology 2e* by OpenStax (Spielman, Jenkins, Lovett),
licensed [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
Access for free at openstax.org. The datasets in this folder are shared under the same license.
