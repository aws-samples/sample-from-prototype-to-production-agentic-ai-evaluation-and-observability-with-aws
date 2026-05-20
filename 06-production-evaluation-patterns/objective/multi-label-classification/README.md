# Multi-Label Classification

This is when a single input can have multiple correct labels at once. Examples: tagging a customer feedback message with multiple categories at the same time, classifying an image with several objects in it, or finding the right set of chunks in a retrieval system.

The key questions become: how many of the correct labels did you find, and how many of the labels you returned were actually correct? This maps to **precision** (of the labels returned, how many were right) and **recall** (of the labels that exist, how many did you find). Multi-label evaluation has a richer set of metrics than single-label because each prediction is a *set* of labels rather than a single label, and the ways those sets can overlap with ground truth give you several useful angles.

## A motivating example: hierarchical customer feedback

Consider a customer feedback agent that ingests messages from a retail business and tags them with multiple categories at once: a product mention (e.g. `product:checkout`, `product:shipping`), a sentiment (`sentiment:negative`), an issue type (`issue:billing`, `issue:delivery`), and an urgency flag (`urgency:high`).

A single feedback message like *"My order arrived two weeks late and I was charged twice for it. This is unacceptable."* should produce a label set like:

```
{ product:shipping, issue:delivery, issue:billing, sentiment:negative, urgency:high }
```

If the agent predicts `{ product:shipping, issue:delivery, sentiment:negative }`, it got 3 out of 5 labels right and missed 2. It is not "wrong", but it is also not "right". Single-label metrics like accuracy don't capture this nuance, which is why multi-label has its own metric family.

## Choosing your metrics

| Metric | What it measures | When to use | What it hides |
|---|---|---|---|
| **Subset accuracy (exact match)** | Fraction of items where the predicted label set exactly equals the ground truth set | You need 100% correctness on every item (e.g. legal categorization) | Partial credit, which is usually what you actually care about |
| **Hamming loss** | Fraction of label assignments that are wrong, averaged across all (item, label) pairs | You want a single number that gives partial credit and treats every label equally | Per-class behavior; rare labels get drowned out |
| **Per-label precision** | For each label, of the items the agent assigned this label, how many actually had it | You care about avoiding false positives on a specific label | Recall on that label |
| **Per-label recall** | For each label, of the items that actually had this label, how many did the agent find | You care about not missing a specific label | Precision on that label |
| **Per-label F1** | Harmonic mean of precision and recall for each label | You want a single number per label that punishes imbalanced precision/recall | Whether the failure is precision-side or recall-side |
| **Macro-averaged F1** | Average of per-label F1, equal weight per label | Imbalanced label frequencies and all labels matter equally | The global picture when label distribution is heavily skewed |
| **Micro-averaged F1** | F1 computed on pooled (item, label) decisions across all labels | You care about overall correctness more than per-label fairness | Whether rare labels are working at all |
| **Jaccard index (IoU) per item** | For each item, size of intersection of predicted and true label sets divided by size of union | You want a single per-item score that gives partial credit and is easy to explain to non-technical stakeholders | Per-label behavior |

**Rule of thumb:** Subset accuracy is almost always too strict for production reporting. Default to per-label F1 plus macro-F1 plus Hamming loss. Add Jaccard if you need a single per-item score for dashboards.

**Watch your rarest labels specifically.** Macro-F1 averages performance across labels, but a label that appears in 2% of samples can have F1 = 0 and barely move the macro number if you have 50 labels. Always read the per-label table alongside any aggregate, and pay extra attention to the bottom three labels by frequency.

## Hierarchical labels need a hierarchical view

The customer feedback example above has structure: `product:*`, `issue:*`, `sentiment:*`, `urgency:*` are not interchangeable categories. Confusing two `product:*` labels is a different kind of error than confusing a `product:*` with a `sentiment:*`.

Two practical patterns for hierarchical multi-label evaluation:

1. **Group-level metrics.** Compute precision, recall, and F1 separately within each label group (`product:*`, `issue:*`, etc.). A model that nails `sentiment:*` but fumbles `issue:*` looks fine on global Hamming loss but tells a clear story when you split by group.

2. **Required vs optional labels.** Some label groups are mandatory for every item (every feedback message has a sentiment), others are optional (not every message has an urgency flag). Score required labels with strict per-label F1 and score optional labels with precision-only (recall is undefined when ground truth is empty).

Hierarchical structure also lets you set group-specific thresholds. If `urgency:high` triggers a human escalation, you might tolerate lower recall on that label (miss some high-urgency items) in exchange for higher precision (avoid false alarms that waste human reviewer time).

## When the classifier is an LLM

Most of the LLM-classifier caveats from [`../single-label-classification/`](../single-label-classification/README.md) apply here too: output variance, prompt sensitivity, no calibrated probabilities, and calibration drift. Multi-label adds two more:

- **Set output is harder for LLMs.** Asking an LLM for "all applicable labels" produces noisier results than asking for "the single best label". The model may over-tag (return every plausible label, hurting precision) or under-tag (stop at the first obvious label, hurting recall). Few-shot examples that include items with 1, 2, 3, and 4 labels each help calibrate the model's set-size behavior.
- **Order and format matter.** A list output `["billing", "delivery"]` and a list output `["delivery", "billing"]` are the same set, but if you are post-processing with a strict parser they may be treated differently. Use a structured output format (JSON with a defined schema) and test parser failures separately from classification failures, so a parsing bug doesn't show up as a recall problem.

## Connection to retrieval

Multi-label classification and retrieval evaluation share the same math. When a RAG system retrieves a set of chunks for a query, the ground truth is a set of relevant chunks, and the question "how many of the correct chunks did you find" is recall, while "how many of the chunks you returned were actually relevant" is precision. The metrics in this section, particularly per-item Jaccard and macro-F1, are exactly the ones used for retrieval evaluation. The metric mechanics are the same; the operational concerns (chunk drift, query rewriting, citation faithfulness) are RAG-specific and live in module 08. See [`../../../08-rag-evaluation/retrieval/`](../../../08-rag-evaluation/retrieval/README.md) for the retrieval-specific framing.

## A self-serve checklist

Before you ship a multi-label classifier to production:

1. ☐ Decide whether subset accuracy matters for your use case. If not, do not report it as the headline number.
2. ☐ Compute per-label precision, recall, and F1. Identify the bottom 3 labels by F1.
3. ☐ Compute macro-F1 and Hamming loss. Reading both together tells you whether the issue is global noise (Hamming) or specific minority-label failures (macro-F1).
4. ☐ If labels are hierarchical, compute group-level metrics on top of per-label metrics.
5. ☐ For every label with F1 below 0.6, read 5 misclassifications and attribute the failure: prompt ambiguity, label noise, model over-tagging, or model under-tagging.
6. ☐ Verify your output parser is not silently dropping valid label sets. Test the parser on synthetic edge cases (empty set, singleton set, full set, malformed JSON).

## When to escalate to human annotation

- Multiple label groups all have macro-F1 below 0.5 → the label schema itself may be the problem; the labels may not be mutually well-defined or the granularity may be wrong. Re-derive the schema with a domain expert before tuning the model.
- A required label group's recall stays below 0.7 across prompt iterations → missing labels will reach production and degrade downstream systems silently. Rewrite the labeling guide with explicit examples and edge cases for the under-recalled labels.
- The agent's predicted set size systematically diverges from the ground truth set size median (consistently 1–2 labels too many or too few) → this is over-tagging or under-tagging, not random error. Prompt rewrites that adjust set-size expectations (with mixed-size few-shot examples) will move the needle faster than swapping models.
