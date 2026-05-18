# Human Alignment

Once you have a [checklist-based rubric](../checklist-based-rubrics/README.md) and an LLM judge scoring your agent's outputs, you need to verify that the automated scores actually agree with what a human expert thinks. This is the calibration loop.

## The process

1. **Get human scores.** Take ~20 sample outputs from your agent and ask a domain expert to score each one. Use a simple scale (1-5 or 1-10), then normalize to 0-1 by dividing by the max. So a score of 7 out of 10 becomes 0.7. You now have 20 normalized human scores between 0 and 1.

2. **Get agent scores.** Run the same 20 samples through your checklist-based rubric (the LLM judge). Normalize the output the same way: divide the total points scored by the maximum possible points. You now have 20 normalized agent scores between 0 and 1.

3. **Check correlation.** Compare the two sets of scores. What matters is not that they are identical, but that they are directionally aligned. If the human gives sample A a higher score than sample B, does the agent agree? Compute the correlation. If it is high (e.g. 0.85+), your rubric is well-calibrated.

4. **Iterate.** If the correlation is low, look at where the disagreements are. Is the LLM judge missing something the human cares about? Add it to the checklist. Is the LLM judge over-weighting something the human does not care about? Reduce the weight or remove it. Then re-run and check correlation again.

5. **Repeat until satisfied.** Keep iterating the checklist items, their weights, and the LLM-as-judge prompt until the correlation with human judgment is at a level you are comfortable with for your use case.

## Why this works

You are not trying to replace human judgment. You are building a trusted proxy that agrees with human judgment often enough that you can run it at scale. A human can only review so many outputs in a day. By doing this calibration work upfront and iterating over time, you make yourself so much more scalable while keeping the performance bar high. You are not flying blind. You have evidence that the LLM judge agrees with your experts, which means you can trust it to evaluate thousands of outputs that no human would ever have time to review. This is what makes your agents trustworthy at production scale.
