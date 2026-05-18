# Retrieval Evaluation

Retrieval evaluation is the most objective part of RAG. Given a query, did you retrieve the right chunks? This maps directly to precision and recall, the same way multi-label classification works: of the chunks you returned, how many were relevant (precision), and of all the relevant chunks that exist, how many did you find (recall)?

Standard IR metrics apply: precision@k, recall@k, NDCG, MRR. You need a ground truth dataset mapping queries to their relevant chunks. Build this by hand for your most important query types and expand it over time as you review production traffic.
