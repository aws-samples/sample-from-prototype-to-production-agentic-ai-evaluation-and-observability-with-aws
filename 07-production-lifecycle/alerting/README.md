# Alerting

Agents fail differently than traditional software. In traditional software, a failed API call throws an error and the user sees an error page. With agents, failures are often implicit rather than explicit. If a tool's API runs out of credits, the tool stops working, but the agent does not necessarily crash. It might move on to the next tool, skip the step, or give a substandard output without raising a visible failure. The user gets a worse answer, but nobody gets paged.

This is why alerting for agents needs to go beyond error rates. You need to monitor tool-level success rates and set thresholds that catch degradation before it compounds.

## Example: Tool pass rate threshold

Say your agent uses a search API tool. You set up a CloudWatch metric tracking tool call success/failure. If the tool has failed 5 out of the last 10 calls, that crosses your threshold. An alarm fires, sends a notification to Slack (via SNS), and the on-call team investigates. They discover the search API ran out of credits. They top it up, and the agent goes back to normal.

Without that alert, you might not notice for a day or two. In the meantime, every user interaction that needed search is getting substandard results, and nobody knows.

## How to implement this

The practical approach is to handle exceptions explicitly in your codebase. When a tool call fails with a specific error (API out of credits, rate limited, timeout), raise and catch that exception, and have that exception trigger an alert. For example, if your search API returns a 402 or 429, catch it, log it as a structured event, and send a Slack notification via SNS. Do not let the agent silently absorb the failure and try to continue without the tool's output.

If you let tool failures pass silently, the agent will try to achieve the outcome anyway. Without the data it needed, it starts to hallucinate and make things up. To the user, the experience suddenly feels broken. "What happened to the agent? It used to be good and now it is making stuff up." That is the worst kind of failure because it erodes trust gradually rather than failing loudly.

## What to alert on

- **Tool call failure rate** - If a specific tool fails above a threshold (e.g. 50% failure over 10 calls), something is wrong with that tool's backend.
- **Specific exception types** - API credit exhaustion, authentication failures, rate limiting. Each should have its own alert path to the right team.
- **Latency spikes** - If a tool or the overall agent response time spikes, it could indicate rate limiting, cold starts, or downstream degradation.
- **Cost anomalies** - If token usage or API costs spike unexpectedly, something changed in the agent's behavior (e.g. looping, excessive retries).

## The goal

Be proactive rather than reactive. Design your alerting so that you catch failures explicitly in code, route them to the right team, and fix them before users notice. Alerting is not optional for production agents. It is what keeps your agent trustworthy.
