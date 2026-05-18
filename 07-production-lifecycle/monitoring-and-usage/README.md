# Monitoring and Usage

Continuous monitoring is not just about catching errors. It is about having full visibility into how your agent is being used, how it is performing, and whether users are actually getting value from it over time.

## What to log

Log every agent interaction: the input, the output, which tools were called, how long each step took, token usage, and which model version was used. This is the raw data that everything else is built on. If you do not log it, you cannot debug it, dashboard it, or replay it later.

## Dashboards

Set up time-series dashboards for the metrics that matter:

- **Latency** - End-to-end response time and time to first token. Are users waiting too long?
- **Error rates by tool** - Which tools are failing and how often? Trends over days and weeks.
- **Token usage and cost** - Is cost per session stable, or is something making the agent use 3x more tokens than last week?
- **Invocation volume** - How many times is the agent being called per day/week?

## User behavior and retention

Technical metrics tell you if the agent is working. Usage metrics tell you if it is useful.

- **Are users coming back?** Track retention. Are users invoking the agent every day, or do they try it once and never return?
- **How often per user?** If a user invokes the agent 5 times a day, that is a strong signal. If they do it once a week, maybe the agent is not solving enough for them.
- **Is usage trending up or down?** A slow decline in daily invocations is a signal that something is off, even if no single alert fires.

These are the signals that tell you whether your agent is actually delivering value, not just running without errors.

## Replay and debugging

A user will come back and say "the agent gave me a wrong answer" or "it said something I did not expect." At that point, you need to be able to go back to that exact conversation, see the state of the system at that moment, and understand exactly what happened. What was the input? What tools were called? What context was available? What did the model return? What was the system prompt at that time?

If you have not logged the state of the system, you will never be able to debug it, and you will never be able to go back to the user with an explanation or a fix. Logging everything is not optional. It is what makes your agent debuggable and your team accountable.

## Periodic quality checks

Pick 10 samples from the past week's traffic, re-run them through your LLM-as-judge rubric, and check that quality is holding. This is not real-time alerting. It is a weekly sanity check that catches slow drift: the agent getting slightly worse over time in ways that no single failure would surface.
