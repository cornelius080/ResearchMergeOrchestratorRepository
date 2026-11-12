"""
agents/sub_agents.py
====================================================================
Definition of specialized research sub-agents.
Configures domain-specific agents for targeted web search.
====================================================================
"""

from config.config import MODEL, DOMAIN_1, DOMAIN_2, DOMAIN_3
from google.adk.agents import Agent
from google.genai import types
from tools.search_tool import duckduckgo_search, before_tool, after_tool


def build_research_instruction(domain: str) -> str:
    """
    Constructs a specialized system instruction for a research agent.

    Args:
        domain (str): The target domain to search.

    Returns:
        str: The formatted system instruction.
    """
    return f"""You are a specialized research agent querying the domain '{domain}'.
Your SOLE responsibility is to call the `duckduckgo_search` tool and return the retrieved articles.

### Query Generation Rules:
1. Extract ONLY 1 to 4 high-level core keywords representing the primary entity and topic (e.g., "NVIDIA" or "NVIDIA AI" 
or "NVIDIA chips").
2. DO NOT include secondary criteria, subtopics, verbs, or filler terms (e.g., do NOT add "roadmap", "partnerships", 
"investments", "ecosystem").
3. Call `duckduckgo_search` passing:
   - `query`: your broad 1-4 keyword string
   - `domain`: '{domain}'

### Execution Rules:
- Do not attempt to synthesize, answer, or filter results using your own knowledge.
- Forward the exact, complete data returned by the tool without any modifications.
"""

agent_config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        thinking_level="minimal",
        include_thoughts=False,
    ),
)

subagent_1 = Agent(
    name="subagent_1",
    model=MODEL,
    generate_content_config=agent_config,
    description=f"DuckDuckGo search assistant for {DOMAIN_1}.",
    instruction=build_research_instruction(DOMAIN_1),
    tools=[duckduckgo_search],
    before_tool_callback=before_tool,
    after_tool_callback=after_tool,
)

subagent_2 = Agent(
    name="subagent_2",
    model=MODEL,
    generate_content_config=agent_config,
    description=f"DuckDuckGo search assistant for {DOMAIN_2}.",
    instruction=build_research_instruction(DOMAIN_2),
    tools=[duckduckgo_search],
    before_tool_callback=before_tool,
    after_tool_callback=after_tool,
)

subagent_3 = Agent(
    name="subagent_3",
    model=MODEL,
    generate_content_config=agent_config,
    description=f"DuckDuckGo search assistant for {DOMAIN_3}.",
    instruction=build_research_instruction(DOMAIN_3),
    tools=[duckduckgo_search],
    before_tool_callback=before_tool,
    after_tool_callback=after_tool,
)
