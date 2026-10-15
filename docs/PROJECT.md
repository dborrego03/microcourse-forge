# Project spec (MVP -> v2)

## Goal
Show, with reproducible evidence, an end-to-end LLM system: retrieval over an open-licensed corpus, structured lesson and quiz generation, continuous evaluation, tracing, and reproducible deployment.

## Scope
- MVP: ingest a small corpus (100-300 pages); chunk; embed; vector retrieval; lesson + quiz as validated JSON with citations; minimal UI; 30-50 evaluation cases; basic traces.
- v1: hybrid search (vector + full text, RRF) and re-ranking; TTS narration with subtitles; SCORM 1.2/2004 export; evals in CI with thresholds; guardrails; Langfuse; Terraform on Azure; tests; 3-minute demo.
- v2: MCP server and bounded agent with human approval; cmi5/xAPI; model and retriever comparison; red-team results.
- Out of scope: multi-user, payments, complex auth, visual course editor, voice cloning, real personal data, restrictively licensed content.

## Pipeline
ingest -> chunk -> embed + index -> retrieve -> generate lesson (JSON, citations) -> generate quiz -> evaluate -> (v1) narrate -> (v1) export.
Each step will emit a trace with latency, tokens and cost.

## Working decisions
- Chunking: split by headings, then by size (starting point: 300-800 tokens, 10-20 % overlap). Measure before tuning.
- Structured output: Pydantic / JSON Schema; retry once returning the validation error to the model; version prompts in the repo.
- Evaluation: three levels (retrieval hit@k and MRR; generation faithfulness and relevance; pedagogical rubric). Start with 30-50 labeled cases.
- Retrieved documents are untrusted data (prompt-injection awareness from day one).

## Data model (PostgreSQL)
documents(id, source_url, title, license, attribution, retrieved_at, content_hash)
chunks(id, document_id, ordinal, section_path, text, token_count, embedding, embedding_model)
courses, lessons, quiz_items, runs, eval_runs, eval_cases (added as the phases need them).

## Licensing
The corpus is OpenStax Psychology 2e, chapters 6 (Learning), 7 (Thinking and Intelligence) and 8 (Memory), licensed CC BY-NC-SA 4.0. Generated lessons are adaptations of the book, so they are non-commercial, shared under the same license and carry the attribution "Access for free at openstax.org". The code is MIT. The book is never committed to the repo. Details and download steps are in docs/corpus.md.
