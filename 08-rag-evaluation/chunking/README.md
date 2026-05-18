# Chunking Evaluation

Chunking is the preprocessing step: how you split documents into pieces before indexing them. Bad chunks lead to bad retrieval regardless of how good your retriever is.

Evaluate chunking by checking: are semantic boundaries preserved (do chunks contain complete thoughts rather than cutting mid-sentence), is the chunk size appropriate for your embedding model's context window, and do chunks retain enough context to be useful in isolation? This is often evaluated qualitatively during development rather than with automated metrics, but poor chunking is a common root cause of RAG failures.
