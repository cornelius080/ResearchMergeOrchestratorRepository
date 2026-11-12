Consider the project in its current state, as represented by the following files.

I would like to introduce a modification to the existing workflow: adding an agent that validates the results returned by the three subagents. Specifically, this agent should be placed after the three subagents have completed their research process and before the merger / synthesis agent.

The agent will take the results produced by the tools executed by the three agents (specifically, `result_tool_subagent_1`, `result_tool_subagent_2`, and `result_tool_subagent_3`) and validate them according to a set of instructions before passing the results to the `merger / synthesis agent`.

The validation process must follow the sequence of instructions below, executed in exactly this order:

1. **Domain validation**: If an article's link does not belong to one of the three **DOMAINs**, the article associated with that link must be discarded from the results. If an article has no link, it must also be discarded. For this check, the agent must consider exclusively the link key.
2. **Date validation**: If an article's publication date is more than four months old, the article must be discarded from the results. In other words, no articles older than four months should be included. If the publication date is unknown, the article must be discarded. Consider whether the agent should have access to a tool that provides the current date to perform this calculation, or whether having access to the machine's current time through `datetime.now` is sufficient. For this check, the agent must consider exclusively the `pub_date` key.
3. **Article relevance validation**: Based on the user query, the agent must determine whether each retrieved article is relevant to that query. For this check, the agent must consider exclusively the title and link keys and evaluate them in relation to the user query. This check should make it possible to eliminate results such as *techcrunch.com/ai*, which do not represent actual articles.

The three checks / validation steps must not modify the content of the articles in any way.

The content key must never be accessed during any of these checks, in order to avoid introducing excessive latency into the workflow.

This sequence of checks must be applied to all results returned by the three agents.

What do you think? If you believe this could improve the quality of the report without introducing excessive latency, create an implementation plan for me to review and approve.

Answer without considering any changes to be made to the `merger / synthesis agent`.