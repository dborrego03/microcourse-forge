# Project spec (MVP -> v2)

## Goal
Show, with reproducible evidence, an end-to-end LLM system: retrieval over an open-licensed corpus, structured lesson and quiz generation, continuous evaluation, tracing, and reproducible deployment.

## Scope
- MVP: ingest a small corpus (100-300 pages); chunk; embed; vector retrieval; lesson + quiz as validated JSON with citations; minimal UI; 30-50 evaluation cases; basic traces.
- v1: hybrid search (vector + full text, RRF) and re-ranking; TTS narration with subtitles; SCORM 1.2 export (2004 dropped: 1.2 imports everywhere and cmi5 covers the modern path); evals in CI with thresholds; guardrails; Langfuse; Terraform on Azure; tests; 3-minute demo.
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

## Data model (PostgreSQL, as built)
- documents(id, title, authors, source_url, license, license_url, attribution, content_hash, ingested_at)
- chunks(id, document_id, ordinal, section_path, pdf_page_start, pdf_page_end, text, token_count, embedding, embedding_model, tsv)
- lessons(id, status, request, lesson, quiz, source_chunk_ids, model, prompt_version, created_at): the quiz lives in the lesson row, and a course is a cmi5 package built from several lessons rather than a table.
- runs(id, lesson_id, step, status, model, tokens_in, tokens_out, cost_usd, latency_ms, retries, cached, error, git_sha, trace_id)
- eval_runs(id, kind, dataset, config, metrics, git_sha, created_at): eval cases live as files in `evals/`, not in the database.
- audio_assets(id, lesson_id, part, provider, model, voice, characters, duration_s, cost_usd, cache_key)

## Licensing
The corpus is OpenStax Psychology 2e, chapters 6 (Learning), 7 (Thinking and Intelligence) and 8 (Memory), licensed CC BY-NC-SA 4.0. Generated lessons are adaptations of the book, so they are non-commercial, shared under the same license and carry the attribution "Access for free at openstax.org". The code is MIT. The book is never committed to the repo. Details and download steps are in docs/corpus.md.
