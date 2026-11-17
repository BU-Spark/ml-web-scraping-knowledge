# Evaluation (planned, not implemented)

How we check that the agent answers correctly, with citations, from the right sources.

Planned contents:
- `questions.jsonl`: demo and test questions, one per line, with the category (1, 2 or 10), the
  expected answer points, and which sources (public URL or internal doc) should support them.
- `run_eval.py`: asks each question through the MCP tools and scores the result.

Things to measure (no targets agreed yet): answer correctness, citation accuracy (does the cited
evidence quote appear in the source?), tool routing (did the question reach the right category
tool?), and whether internal-only answers are withheld from users without access.

Segmentation (category 2) is the demo focus, so start there. Do not put real internal text in
this folder: reference internal docs by `doc_id` only.
