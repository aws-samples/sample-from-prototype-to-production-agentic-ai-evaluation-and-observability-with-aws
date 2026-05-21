# Multi-Label Classification

This is when a single input can have multiple correct labels. Examples: tagging a document into several categories, object detection (multiple objects in one image), or finding the right set of chunks in a retrieval system.

The key questions become: how many of the correct labels did you find, and how many of the labels you returned were actually correct? This maps to precision (of the labels returned, how many were right) and recall (of the labels that exist, how many did you find). RAG retrieval evaluation often falls into this pattern: given a query, did you retrieve the right chunks, and did you get all of them?
