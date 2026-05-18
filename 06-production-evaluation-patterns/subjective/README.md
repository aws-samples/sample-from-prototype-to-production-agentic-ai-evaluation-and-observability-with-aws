# Subjective Agents

A subjective agent produces outputs where there is no single correct answer. The quality of the output depends on human judgment, taste, and domain expertise. You cannot write a formula to determine if the output is "right." Examples: deep research agents, website builders, slide generators, creative writing assistants, and general-purpose chat agents.

The challenge is: how do you evaluate something that has no ground truth? The answer is to make the subjective as structured and repeatable as possible, without pretending it is objective. There are two main approaches:

- **Checklist-based rubrics** - Break "is it good?" into a weighted list of specific criteria. For example, a deep research report might score +2 points for mentioning a key concept, +5 points for covering a critical detail. The LLM judge checks each item and gives you a numeric score. The checklist is different for every agent and use case, but the pattern is the same: define what matters, weight it, score against it.
- **Human alignment** - The checklist itself needs to be calibrated against what domain experts actually care about. Collect human ratings, compare them to your automated scores, and check the correlation. What matters is not that the exact scores match, but that they are directionally the same. If the agent scores three items as 7, 10, and 9, and the human scores them 6, 9, and 8, the correlation is near perfect. As long as both agree on which outputs are better and which are worse, your evaluation is working properly. Track this correlation over time as the system evolves.

Navigate into the subfolders for detailed examples and implementation patterns.
