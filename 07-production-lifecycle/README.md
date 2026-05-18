# Production Lifecycle

Your agent is deployed and serving real users. Now what? This module covers how to safely evolve a production agent over time: updating system prompts, rolling out changes without breaking things, monitoring for regressions, and responding when something goes wrong.

**The core pattern is: make a change, validate it is better or at least not worse, then promote or rollback.**

How you validate depends on your setup. You might run internal evals against your most common use cases, compare old vs new outputs with LLM-as-judge or human review, and ship directly to production if the results are good. Or you might A/B test by routing a small percentage of live traffic to the new version and measuring in production. Or both. The right approach depends on how good your offline evaluation is, your risk tolerance, and the agent use case.

In production, agents have to solve for a business case. That means you will inevitably face scenarios like:

- **Updating the system prompt** - You want to add a new capability or change how the agent behaves. How do you validate the new prompt does not regress on existing behavior?
- **Swapping a backend API** - Your research agent uses Brave Search but you want to switch to a different SERP API. To the agent, nothing has changed. The tool interface is identical. But internally, the backend is different and the results may differ. How do you ensure quality stays the same?
- **Modifying tool schemas** - Tool schemas define how your agent parses input and passes it to the tool. Changing the input structure, output structure, or description changes how the agent interacts with your infrastructure. Small schema changes can shift behavior in unpredictable ways.
- **Optimizing model selection for cost and performance** - The agent works great on Opus 4.7 but costs too much. How do you get the same performance with a smaller, cheaper model like Sonnet or Haiku?
- **Reducing latency** - Smaller models are faster. How do you find the sweet spot where the agent is both quick and capable enough for your use case?

Each of these is a real scenario that production teams face. The subfolders here cover the mechanisms (A/B testing, weighted routing, monitoring, alerting) for handling these changes safely.
