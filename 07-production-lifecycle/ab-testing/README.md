# A/B Testing

You have two versions of the same agent. Maybe version B has a new tool, a new feature, a change to the system prompt, or a different model. You have run your offline evaluations and testing looks good. Now you are ready to take this to production. But do you just flip from A to B for everyone at once?

The better approach is A/B testing. You turn on the new version for a certain percentage of your users, say 10%, and keep the remaining 90% on the proven version. Those 10% of users interact with the new agent in production, and you monitor those conversations, observe the outputs, and check that the new version is performing well on real traffic. Once you are comfortable, you increase the percentage. If something goes wrong, you route everyone back to version A.

## Design your systems for change

The most important takeaway is not the A/B test itself, but the principle behind it: **design your systems in a way that you can serve a certain part of your user base with new changes.** If your architecture does not support routing different users to different agent versions, you are stuck with all-or-nothing deployments. That is risky.

This means building your system with a routing layer (feature flags, traffic splitting, or gateway rules) that lets you:

- Serve the updated agent to a subset of the population
- Monitor those conversations separately from the baseline
- Roll back instantly if the new version underperforms
- Gradually increase traffic as confidence grows

This is not just about testing. It is about making your production agent systems resilient to change. Agents evolve constantly (new prompts, new tools, new models), and the teams that ship safely are the ones who built the infrastructure to do partial rollouts from day one.

## What to measure

"Better" for agents is often multi-dimensional: faster, more accurate, more helpful, cheaper. Pick which metrics are your primary decision criteria upfront. Do not change multiple things at once or you will not know what caused the difference. Monitor the new version against the same evaluation criteria you used in your offline evals, but now on real user traffic.
