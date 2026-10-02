---
name: design-rag
description: Designs ingestion, chunking, retrieval, citations, and retrieval evaluation for a RAG use case. Use when planning semantic search or grounded answering.
---

# Design RAG

Design the path from documents to grounded context, including how you will know retrieval works.

## Workflow

1. State the use case and what a correct source looks like.
2. Describe the corpus: size, formats, permissions, and update rate. Mark assumptions.
3. Choose ingestion and parsing that preserve the structure the answer needs.
4. Normalize content and metadata required for filters and citations.
5. Choose a chunking strategy and what it will get wrong.
6. Choose an embedding model and what is versioned with it.
7. Define retrieval and metadata filters, especially permission filters.
8. Add hybrid search or reranking only as a hypothesis to evaluate, not as a default.
9. Define how context is assembled and how citations point at returned sources.
10. Define the evaluation set and metrics: Recall@K, Precision@K, MRR, NDCG, citation recall, and citation precision, dropping only those that do not fit, with a reason.

Use the run-evals skill when it is time to execute that plan. Use `docs/templates/evaluation-plan.md`.

## Prohibitions

Do not finish the design without an evaluation strategy. Do not index content the caller is not allowed to retrieve.
