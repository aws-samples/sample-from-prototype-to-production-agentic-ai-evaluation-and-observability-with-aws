# Checklist-Based Rubrics

When you cannot reduce evaluation to a single number, break it into a checklist. Each item on the checklist is a specific, answerable question about the output. This turns a vague "is it good?" into a set of concrete criteria that you can score.

## Example: Deep Research Agent

Say you have a deep research agent. You ask it: "How does Amazon Bedrock AgentCore handle security isolation between users when multiple agents share the same runtime infrastructure?"

This is a real research question that requires synthesizing information across multiple parts of the AgentCore documentation: Runtime sessions, microVM isolation, IAM authentication, Policy enforcement via Cedar, and Gateway interceptors. The agent explores, follows different paths, and produces a report. Every time you invoke the agent, the report will be different because it can approach the topic from different angles. There is no single correct answer. But what matters is: does it contain the facts that are important for this topic?

This is where the checklist comes in. You define the things that matter for this particular question, and you weight them:

| Checklist item | Weight |
|---|---|
| Mentions that each session runs in a dedicated microVM with isolated CPU, memory, and filesystem | +5 points |
| Explains that after session termination, the microVM is destroyed and memory is sanitized | +4 points |
| Covers inbound authentication (SigV4 or OAuth 2.0 token validation before requests reach the agent) | +3 points |
| Mentions Policy in AgentCore using Cedar to enforce fine-grained tool access per principal | +4 points |
| Explains that Gateway interceptors can inspect and block requests before they reach tool targets | +3 points |
| Notes that sessions are identified by runtimeSessionId and a new session ID after termination creates a fresh environment | +2 points |
| Mentions that session state is ephemeral and long-term durability requires AgentCore Memory | +2 points |

Total possible: 23 points.

When you evaluate, the LLM judge goes through the output and checks each item. One report might cover microVM isolation and Cedar policies (+9 points). Another might cover all seven items (+23 points). You now have a numeric score for something that seemed entirely subjective, because you broke it down into the things that matter for this question.

## The key point

The specific checklist items and their weights will be different for every agent you build and for every question you evaluate against. A deep researcher about AgentCore security has different criteria than a deep researcher about AgentCore pricing or AgentCore Memory strategies. The pattern is the same (define what matters, weight it, score against it), but the content of the checklist is specific to your agent and your use case. You are the one who defines what "good" looks like for your particular problem.
