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
- Code: MIT.
- Source content: OpenStax *Psychology 2e*, CC BY-NC-SA 4.0. Access for free at openstax.org.
- Generated lessons and quizzes are adaptations of that book and are shared under CC BY-NC-SA 4.0.

See [docs/corpus.md](docs/corpus.md).
