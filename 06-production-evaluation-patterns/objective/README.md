# Objective Agents

An objective agent is one where the output has a measurable ground truth. You can write code or apply a formula to determine whether the agent got it right. This is your classical data science evaluation territory.

Subtypes:

- **Single-label classification** - One correct label per item. Accuracy for balanced datasets, F1/precision/recall for imbalanced ones.
- **Multi-label classification** - Multiple correct labels per item. Document tagging, object detection, or finding the right set of items from a larger pool.
- **Regression** - Continuous numeric outputs. L2 loss, RMSE.
- **Structured output with LLM-as-judge** - The output is structured (JSON, schema-conforming) and you use an LLM judge to verify correctness. Still objective because there is something tangible to measure against.
