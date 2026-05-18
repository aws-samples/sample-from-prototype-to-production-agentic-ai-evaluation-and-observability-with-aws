# RAG Evaluation

RAG (Retrieval-Augmented Generation) has two distinct steps, and each one needs to be evaluated separately:

1. **Retrieval** - Finding the right chunks from your knowledge base. This is objective. You can measure it with precision and recall: did you find the right chunks, and how many of the relevant ones did you get? This is the same pattern as multi-label classification.
2. **Generation** - Using an LLM to synthesize an answer from the retrieved chunks. This is where it gets subjective. Was the answer well-written? Did it actually use the context? Did it hallucinate beyond what was retrieved?

Because these two steps require completely different evaluation strategies, you should never only measure the final output. If the chunks were never retrieved properly, the model was never given the right context, and the final answer can never be as good. That is a retrieval problem. On the other hand, if the right chunks were retrieved but the final answer fails to follow the tone, branding, or style you expect, that is a generation problem. Separating these two tells you where to focus your effort. The subfolders here break this down layer by layer.
