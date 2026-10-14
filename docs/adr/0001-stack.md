# ADR-001: Stack for the MVP

Status: accepted

## Decision
- Core (ingestion, retrieval, generation, evals): Python + FastAPI + Pydantic
- UI: Next.js (TypeScript)
- Storage: PostgreSQL + pgvector
- LLM provider: OpenAI API behind a provider interface (Azure OpenAI later)
- Corpus: OpenStax Psychology 2e, chapters 6, 7 and 8 (see docs/corpus.md)
- Corpus license: CC BY 4.0. Attribution required ("Access for free at openstax.org"); no non-commercial or share-alike restriction.
- Language: lessons are generated in English in the MVP.

## Consequences
- Every document and chunk records its license and attribution in the database.
- The source book is not stored in the repo; docs/corpus.md explains how to download it.
