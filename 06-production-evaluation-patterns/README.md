# Production Evaluation Patterns

The first question to answer when evaluating an AI agent is: **what type of agent is it?**

We classify agents into two categories based on whether their output has a measurable ground truth:

- **Objective agents** are quantitative. Their outputs can be measured with code or math. There is a correct answer, and you can compute how close the agent got to it. Examples: a classification agent that routes support tickets to departments, a pricing agent that predicts product values, a tagging agent that labels documents into categories, or an extraction agent that pulls structured fields from contracts. You evaluate these the same way a data scientist evaluates a model: accuracy, precision, recall, F1, RMSE, etc.
- **Subjective agents** are qualitative. Their outputs have no single right answer, and evaluation is more vibes-based. Examples: deep research agents, website builders, slide generators, creative writing assistants. You evaluate these through alignment with human preferences, checklist-based rubrics, and domain expert review.

Start by identifying which category your agent falls into, then navigate into the appropriate folder for specific evaluation strategies and metrics.
