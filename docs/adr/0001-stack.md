# ADR-001: Stack for the MVP

Status: accepted (2026-10-14)

## Context
The goal is a small but complete RAG system whose quality can be measured: ingest an open-licensed book, retrieve passages, generate lessons and quizzes as JSON, and score the output in CI. It has to run locally with Docker first and move to Azure later. Time is limited (about 9 h a week), so the stack should be boring where possible and new only where learning it is part of the point.

## Options considered
- **Core language.** Python vs TypeScript (Vercel AI SDK). I know TypeScript better, but the eval tooling (RAGAS, DeepEval) and the MCP SDK are Python-first, and most applied-AI job posts ask for Python.
- **Vector store.** PostgreSQL + pgvector vs Azure AI Search, Pinecone or Weaviate. A dedicated vector DB is one more service to run and pay for. At a few thousand chunks Postgres is more than enough, and it keeps documents, chunks, runs and eval results in one place where plain SQL works. Azure AI Search stays on the list as a comparison for v2.
- **LLM provider.** OpenAI API vs Azure OpenAI. OpenAI is quicker to start with. Calls go through a small provider interface so switching to Azure OpenAI later is a config change, not a rewrite.

## Decision
- Core (ingestion, retrieval, generation, evals): Python, FastAPI, Pydantic
- UI: Next.js with TypeScript, kept minimal
- Storage: PostgreSQL + pgvector
- LLM: OpenAI API behind a provider interface; Azure OpenAI later
- Corpus: OpenStax *Psychology 2e*, chapters 6-8, licensed CC BY-NC-SA 4.0 (see docs/corpus.md)
- Lessons are generated in English for the MVP

## Consequences
- Every document and chunk stores its license and attribution in the database, so generated lessons can carry them.
- Because of the share-alike clause, anything generated from the book is published under CC BY-NC-SA 4.0. The code stays MIT.
- The book itself is never committed; docs/corpus.md explains how to download it.
- Python tooling is new to me in parts (pytest, async FastAPI, Alembic), which is accepted as part of the work.
