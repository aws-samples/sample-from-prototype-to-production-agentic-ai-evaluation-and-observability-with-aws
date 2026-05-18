# End-to-End Evaluation

End-to-end evaluation treats the RAG pipeline as a black box: given a question, did the system produce the right answer? This does not tell you which component failed, but it tells you whether the system works from the user's perspective.

Use this as a top-level smoke test and regression check. Maintain a set of question-answer pairs with known correct answers. Run them through the full pipeline periodically and flag any regressions. When an end-to-end test fails, drill into the per-layer evaluations (retrieval, grounding, synthesis) to diagnose the root cause.
