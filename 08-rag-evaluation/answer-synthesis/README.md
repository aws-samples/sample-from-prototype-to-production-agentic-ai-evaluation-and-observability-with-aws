# Answer Synthesis Evaluation

Answer synthesis evaluates the quality of the final generated response, assuming retrieval and grounding are already correct. This is the subjective layer of RAG: was the answer well-written, did it combine multiple sources coherently, and did it actually address the user's question?

This layer uses the same techniques as subjective agent evaluation: checklist-based rubrics, LLM-as-judge with explicit criteria, and human review for calibration. The difference from general subjective evaluation is that you have the retrieved context as additional input, so the judge can check relevance and completeness against the available information.
