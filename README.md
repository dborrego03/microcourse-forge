# microcourse-forge
AI micro-course generator with measurable quality: RAG over an open-licensed corpus, structured lessons and quizzes, evals in CI, tracing, and Terraform on Azure.

Status: work in progress (MVP in progress).

## Quickstart
```
docker compose up -d
```

## Roadmap
- MVP: ingestion, retrieval, lesson + quiz generation, minimal UI
- v1: hybrid search + reranking, audio, SCORM export, evals in CI, tracing, IaC
- v2: MCP server, agent with approval, cmi5/xAPI

## License
Code: MIT. Content: OpenStax Psychology 2e (CC BY 4.0), "Access for free at openstax.org". See docs/corpus.md.
