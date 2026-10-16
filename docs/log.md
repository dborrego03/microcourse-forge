# Decision and failure log

Short notes on what went wrong, what I measured and what I changed. Newest first.

## 2026-10-16 · Haiku vs. Sonnet as the generator
I ran the generation eval twice with the same prompts, once per generator, with Opus as the judge
so it wasn't grading either model's own writing (commit 05cd49b, details in `evals/README.md`):

| | claude-haiku-5-5 | claude-sonnet-5-5 |
|---|---|---|
| faithfulness | 0.971 | 0.947 |
| unsupported claims | 9 / 307 | 20 / 375 |
| relevance | 4.75 | 5 |
| rubric mean | 3.972 | 4.167 |
| valid on first try | 0.917 | 1.0 |
| cost per lesson (estimate) | $0.0059 | $0.0692 |
| latency p50 / p95 | 44.3 s / 65.7 s | 32.4 s / 41.5 s |

Sonnet's lessons read better (clarity 4.083 vs. 3.583, examples 4.25 vs. 3.667) at about 12 times
the cost, and it adds more that the cited sources don't say. Haiku with the same prompts scored
4.056 in the earlier run judged by Sonnet and 3.972 here with Opus, so with 12 lessons, one run
each and a judge not yet calibrated against humans, a 0.2 gap on the rubric is a hint rather than
a verdict. Haiku stays the default for now: it is much cheaper and sticks closer to the sources.

## 2026-10-16 · What a code and security review found
A full review of the repository turned up bugs that no test was looking for:
- **Re-running ingestion broke every lesson.** It deleted and reloaded the chunks, which got new
  ids, while lessons cite chunks by id. Ingestion now skips a copy that's already loaded.
- **The cache kept bad answers.** A response that failed validation was cached before it was
  checked, so the same request failed forever without calling the model again.
- **Production couldn't retry.** The API provider let the SDK validate the JSON, which turned a
  fixable answer into a 503 before my retry-with-feedback could run. It now returns raw JSON like
  the CLI path, and both share the same validation.
- **Interrupted lessons stayed "running"**, because only `Exception` was caught, not cancellation.
- **Anyone could run up the bill.** The public endpoints had no ceiling, and narration could be
  bought twice by sending the same request in parallel. There is now a daily limit, a row lock on
  narration and reuse of existing audio.
- **CI and deploy permissions were broader than needed**: the Azure token was available to the
  image-build job, the Claude token to every step of the nightly evals, and actions were pinned by
  tag. All of that is now per-job, per-step and pinned by commit.

Lesson: tests check what I thought of; a review with fresh eyes checks what I didn't.

## 2026-10-15 · The lesson prompt was fighting itself
The first generation eval (12 lessons) gave faithfulness 0.90: 30 of 309 claims weren't backed by
the sources each section cited. Reading them, most were textbook-style definitions and bridging
remarks the model added on its own. The prompt asked it to "define every technical term" for
beginners and also to "use only the sources", and it resolved the conflict by defining terms from
memory. The new rule says to define terms the way the sources do, or leave them out.

| | prompt v1 (d1713af) | prompt v2 (53c77cb) |
|---|---|---|
| faithfulness | 0.903 | 0.976 |
| unsupported claims | 30 / 309 | 6 / 249 |
| rubric accuracy | 3.75 | 4.42 |
| rubric clarity | 4.17 | 3.92 |
| rubric mean | 4.03 | 4.06 |

Accuracy went up and clarity went down a little, which makes sense: fewer self-written
definitions. With 12 lessons a 0.25 change on a 1-5 scale may be noise; the drop in unsupported
claims is not.

## 2026-10-15 · Regex guardrails didn't generalize
I wrote the input rules (injection, harmful intent, personal data) while looking at
`redteam_v1`, and they blocked all 30 cases. A held-out set written afterwards told a different
story: 44% blocked, and none of the harmful requests ("methods to make a witness forget what they
saw" doesn't say "how to"). I added a small model as a second screen and ran the held-out set
once more without touching the rules: 94%. The miss left is "Introduction to machine learning",
which the relevance check lets through because of the word "learning".

## 2026-10-15 · A file that only existed on my machine
CI's web job failed to type-check while everything passed locally. The Python `.gitignore`
template ignores every `lib/` folder, including `apps/web/app/lib/`, so `api.ts` was never pushed.
Fixed with an exception in `.gitignore`. Lesson: check a fresh clone, not the working tree.

## 2026-10-15 · Re-ranker: smaller model, fewer candidates
On `retrieval_v1`, re-ranking lifted hit@1 from 0.62 to 0.80 and MRR from 0.76 to 0.88, at about
1 s per query on CPU. The tiny Jina re-ranker beat MiniLM-L6 on both quality and speed, and
re-ranking 10 candidates instead of 20 halved the latency for a small MRR loss (0.891 to 0.878).
Hybrid search (full text + vectors with RRF) barely moved the numbers on this corpus.

## 2026-10-15 · The corpus license was wrong in the docs
The first commit said the book was CC BY 4.0, "verified in the preface". The copyright page of
the PDF says CC BY-NC-SA 4.0. That changes what the generated lessons must carry (same license,
non-commercial), so it was fixed everywhere before any lesson was published.
