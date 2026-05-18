# Grounding Evaluation

Grounding checks whether the LLM actually used the retrieved context rather than hallucinating or relying on its parametric knowledge. The question is: can every claim in the response be traced back to the retrieved chunks?

This is semi-objective. You can decompose the response into individual claims, then verify each claim against the provided context. An LLM judge works well here because the task is constrained: "is this specific claim supported by this specific text?" It is not a taste judgment, it is a verification task with a clear yes/no answer per claim.
