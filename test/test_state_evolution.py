"""
test/test_state_evolution.py
====================================================================
End-to-end multi-agent workflow test script with explicit state tracking.
Monitors session state mutations across all agent and tool callbacks,
adopting the same architecture of the project.
====================================================================
"""

import asyncio
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to sys.path so config package can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.adk.agents import Agent
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from config.config import MODEL, MODEL_LCW


# ====================================================================
# State Tracing Utility
# ====================================================================
def delete_state_key(state: Any, key: str) -> None:
    """
    Safely purges a key from Google ADK State or a standard dict,
    removing it from internal tracking structures (_delta and _value).
    """
    if state is None:
        return

    # If it is a standard Python dict
    if isinstance(state, dict):
        state.pop(key, None)
        return

    # If it is a Google ADK State tracking object
    if hasattr(state, "_delta") and isinstance(state._delta, dict):
        state._delta.pop(key, None)
    if hasattr(state, "_value") and isinstance(state._value, dict):
        state._value.pop(key, None)


def print_state_snapshot(event_label: str, state: Any) -> None:
    """
    Prints a formatted, readable snapshot of the session state at every
    context transition, safely handling both dict and Google ADK State objects.
    """
    print("\n" + "=" * 80)
    print(f"🔄 [STATE SNAPSHOT] -> Event: {event_label.strip()}")
    print("=" * 80)

    # Safely convert Google ADK State object to a standard dict
    if state is None:
        state_dict = {}
    elif hasattr(state, "to_dict"):
        state_dict = state.to_dict()
    elif isinstance(state, dict):
        state_dict = state
    else:
        try:
            state_dict = dict(state)
        except Exception:
            state_dict = getattr(state, "__dict__", {})

    if not state_dict:
        print("  (State is currently empty)")
    else:
        for key, value in state_dict.items():
            if isinstance(value, list):
                print(f"  • {key} (List, total items: {len(value)}):")
                for idx, item in enumerate(value):
                    if isinstance(item, dict):
                        print(f"      [{idx}] {item.get('title')} | pub_date: {item.get('pub_date')}")
                    else:
                        print(f"      [{idx}] {item}")
            elif isinstance(value, dict):
                formatted_dict = json.dumps(value, indent=6)
                print(f"  • {key} (Dict):\n{formatted_dict}")
            elif isinstance(value, str) and len(value) > 120:
                print(f"  • {key} (Str, preview): {value[:115]}...")
            else:
                print(f"  • {key}: {value}")
    print("=" * 80 + "\n")


# ====================================================================
# Mock Data Store (10 items per subagent, dates 2025.01.01 - 2026.12.31)
# ====================================================================
MOCK_DATABASE = {
    "subagent_1": [
        {"title": "DeepSeek-V3 Open-Weights Architecture Breakdown", "pub_date": "2026-10-12"},
        {"title": "Mixture-of-Experts Scaling Laws in Foundation Models", "pub_date": "2026-08-25"},
        {"title": "Llama 3.3 70B Benchmark Performance Comparison", "pub_date": "2026-06-18"},
        {"title": "FlashAttention-4 Integration in Transformer Training", "pub_date": "2026-03-04"},
        {"title": "Sparse Attention Mechanisms for Efficient Inference", "pub_date": "2026-01-15"},
        {"title": "Early Experiments in Multi-Token Prediction Architectures", "pub_date": "2025-11-20"},
        {"title": "Survey of Low-Rank Adaptation Techniques (LoRA)", "pub_date": "2025-08-14"},
        {"title": "DeepSpeed ZeRO-3 Optimization on Consumer Hardware", "pub_date": "2025-05-30"},
        {"title": "Quantization Strategies for Edge LLM Deployments", "pub_date": "2025-03-12"},
        {"title": "Introduction to Reinforcement Learning with Human Feedback", "pub_date": "2025-01-22"},
    ],
    "subagent_2": [
        {"title": "NVIDIA Blackwell Ultra B300 Data Center Shipments Begin", "pub_date": "2026-09-30"},
        {"title": "Cerebras CS-3 WSE Wafer-Scale AI Supercomputer Launch", "pub_date": "2026-07-14"},
        {"title": "Groq LPUs Scale Ultra-Fast Real-Time Inference Clouds", "pub_date": "2026-04-20"},
        {"title": "SambaNova SN40L Hardware Acceleration in Enterprise Clouds", "pub_date": "2026-02-10"},
        {"title": "HBM3e Memory Shortages and Semiconductor Supply Chains", "pub_date": "2025-12-05"},
        {"title": "NVIDIA Hopper H200 141GB Memory Benchmark Tests", "pub_date": "2025-09-18"},
        {"title": "AMD Instinct MI300X Production Ramp and Hyperscaler Deals", "pub_date": "2025-06-28"},
        {"title": "Liquid Cooling Deployments Expand Across AI Data Centers", "pub_date": "2025-04-10"},
        {"title": "Intel Gaudi 3 AI Accelerator Architecture and Pricing", "pub_date": "2025-02-17"},
        {"title": "Venture Investments in Specialized Silicon Startups Overview", "pub_date": "2025-01-05"},
    ],
    "subagent_3": [
        {"title": "EU AI Act Compliance and Open-Weights Model Licensing", "pub_date": "2026-10-02"},
        {"title": "Autonomous Coding Agent Frameworks Enter Enterprise Production", "pub_date": "2026-08-01"},
        {"title": "Security Benchmarks for Multi-Agent Tool-Calling Systems", "pub_date": "2026-05-19"},
        {"title": "Open-Weights Model Ecosystem Trends and Global Adoption", "pub_date": "2026-02-28"},
        {"title": "Decentralized Model Weights Repositories and Data Sovereignty", "pub_date": "2025-10-15"},
        {"title": "Standardization of Function-Calling Formats Across Model Providers", "pub_date": "2025-07-22"},
        {"title": "Analysis of Prompt Injection Vulnerabilities in Agentic Pipelines", "pub_date": "2025-04-30"},
        {"title": "Open Source vs Proprietary Model Performance Gap Closes", "pub_date": "2025-03-08"},
        {"title": "Federal Trade Commission Inquiries into Major Cloud Compute Deals", "pub_date": "2025-02-01"},
        {"title": "Review of Emerging Open Model Licenses for Commercial Use", "pub_date": "2025-01-18"},
    ],
}


def search_tool(query: str, tool_context: ToolContext) -> List[Dict[str, str]]:
    """
    Simplified mock search tool returning 10 articles with 'title' and 'pub_date'.
    """
    agent_name = tool_context.agent_name if tool_context else "subagent_1"
    return MOCK_DATABASE.get(agent_name, [])


def before_tool(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext) -> None:
    """Tracks subagent tool query and prints state."""
    agent_name = tool_context.agent_name
    query = args.get("query", "")
    tool_context.state[f"query_{agent_name}"] = query
    print_state_snapshot(f"\n\nbefore_tool ({agent_name})", tool_context.state)
    return None


def after_tool(tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext, tool_response: Any) -> None:
    """Records raw tool results into state and prints state."""
    agent_name = tool_context.agent_name
    tool_context.state[f"result_tool_{agent_name}"] = tool_response
    tool_context.actions.skip_summarization = True
    print_state_snapshot(f"\n\nafter_tool ({agent_name})", tool_context.state)
    return None


# ====================================================================
# Sub-Agents Definition
# ====================================================================
agent_config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        thinking_level="minimal",
        include_thoughts=False,
    ),
)

subagent_instruction = (
    "You are a search assistant. Analyze the user request and make EXACTLY ONE "
    "consolidated call to search_tool. Do not perform secondary or follow-up searches."
)

subagent_1 = Agent(
    name="subagent_1",
    model=MODEL,
    generate_content_config=agent_config,
    description="Search subagent 1.",
    instruction=subagent_instruction,
    tools=[search_tool],
    before_tool_callback=before_tool,
    after_tool_callback=after_tool,
)

subagent_2 = Agent(
    name="subagent_2",
    model=MODEL,
    generate_content_config=agent_config,
    description="Search subagent 2.",
    instruction=subagent_instruction,
    tools=[search_tool],
    before_tool_callback=before_tool,
    after_tool_callback=after_tool,
)

subagent_3 = Agent(
    name="subagent_3",
    model=MODEL,
    generate_content_config=agent_config,
    description="Search subagent 3.",
    instruction=subagent_instruction,
    tools=[search_tool],
    before_tool_callback=before_tool,
    after_tool_callback=after_tool,
)

parallel_research_agent = ParallelAgent(
    name="ParallelWebResearchAgent",
    sub_agents=[subagent_1, subagent_2, subagent_3],
    description="Runs 3 research subagents in parallel.",
)


# ====================================================================
# Validator Agent (Keeps ONLY 2026 articles, discards 2025)
# ====================================================================
def clean_and_parse_json(raw_text: str) -> Dict[str, Any]:
    """Extracts JSON payload safely even if wrapped in markdown code blocks."""
    if not raw_text:
        return {}
    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    else:
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text, flags=re.DOTALL).strip()
        brace_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if brace_match:
            text = brace_match.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        return {}


def before_validator_agent(callback_context: CallbackContext) -> None:
    """Prepares formatted candidate records for the validator and prints state."""
    raw_1 = callback_context.state.get("result_tool_subagent_1") or []
    raw_2 = callback_context.state.get("result_tool_subagent_2") or []
    raw_3 = callback_context.state.get("result_tool_subagent_3") or []

    def _format(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "No items."
        return "\n".join([f"[{i}] {item.get('title')} | pub_date: {item.get('pub_date')}" for i, item in enumerate(items)])

    callback_context.state["candidate_records_subagent_1"] = _format(raw_1)
    callback_context.state["candidate_records_subagent_2"] = _format(raw_2)
    callback_context.state["candidate_records_subagent_3"] = _format(raw_3)

    print_state_snapshot("\n\nbefore_validator_agent", callback_context.state)
    return None


def after_validator_agent(callback_context: CallbackContext) -> None:
    """Filters tool records keeping ONLY 2026 items and prints state."""
    raw_output = callback_context.state.get("validator_output", "")
    parsed = clean_and_parse_json(raw_output)

    indices_1 = parsed.get("subagent_1_indices", [])
    indices_2 = parsed.get("subagent_2_indices", [])
    indices_3 = parsed.get("subagent_3_indices", [])

    raw_1 = callback_context.state.get("result_tool_subagent_1") or []
    raw_2 = callback_context.state.get("result_tool_subagent_2") or []
    raw_3 = callback_context.state.get("result_tool_subagent_3") or []

    # Filter strictly keeping only 2026 validated articles
    valid_1 = [raw_1[i] for i in indices_1 if 0 <= i < len(raw_1)]
    valid_2 = [raw_2[i] for i in indices_2 if 0 <= i < len(raw_2)]
    valid_3 = [raw_3[i] for i in indices_3 if 0 <= i < len(raw_3)]

    callback_context.state["result_tool_subagent_1_validated"] = valid_1
    callback_context.state["result_tool_subagent_2_validated"] = valid_2
    callback_context.state["result_tool_subagent_3_validated"] = valid_3

    # ====================================================================
    # Safe Destruction: Purge temporary candidate records from state
    # ====================================================================
    temp_keys_to_delete = [
        "result_tool_subagent_1",
        "result_tool_subagent_2",
        "result_tool_subagent_3",
        "candidate_records_subagent_1",
        "candidate_records_subagent_2",
        "candidate_records_subagent_3",
        "validator_output",
    ]
    for key in temp_keys_to_delete:
        delete_state_key(callback_context.state, key)

    print_state_snapshot("\n\nafter_validator_agent", callback_context.state)
    return None


validator_agent = Agent(
    name="validator_agent",
    model=MODEL,
    generate_content_config=agent_config,
    output_key="validator_output",
    before_agent_callback=before_validator_agent,
    after_agent_callback=after_validator_agent,
    instruction="""
You are the Validator Agent.
Your task is to inspect the candidate articles and KEEP ONLY those with pub_date in the year 2026.
Any article published in 2025 MUST BE DISCARDED.

Candidate Lists:
* Subagent 1:
{candidate_records_subagent_1}

* Subagent 2:
{candidate_records_subagent_2}

* Subagent 3:
{candidate_records_subagent_3}

Output ONLY a JSON block listing the integer indices of the valid 2026 articles:
```json
{
  "subagent_1_indices": [0, 1, 2],
  "subagent_2_indices": [0, 3],
  "subagent_3_indices": [1]
}
if a subagent has no 2026 articles, return an empty list for that subagent. Do not write text outside the JSON.
""",
description="Validates articles keeping strictly 2026 publications.",
)

#====================================================================
#Merger / Synthesis Agent (Displays validated lists with intro)
#====================================================================
def before_merger_agent(callback_context: CallbackContext) -> None:
    """Logs state immediately before the synthesis merger runs."""
    print_state_snapshot("\n\nbefore_merger_agent", callback_context.state)
    return None

def after_merger_agent(callback_context: CallbackContext) -> None:
    """Logs state immediately after the synthesis merger runs."""
    print_state_snapshot("\n\nafter_merger_agent", callback_context.state)
    return None

merger_agent = Agent(
    name="merger_agent",
    model=MODEL_LCW,
    generate_content_config=types.GenerateContentConfig(
        max_output_tokens=16384,
        #temperature=0.2,
        thinking_config=types.ThinkingConfig(
            thinking_level="low",
            include_thoughts=False,
        ),
    ),
    output_key="final_response",
    before_agent_callback=before_merger_agent,
    after_agent_callback=after_merger_agent,
    instruction="""
    You are the Merger Synthesis Agent.
    Provide a brief introductory sentence, and then clearly print the validated 2026 articles for Subagent 1, Subagent 2, 
    and Subagent 3 using the inputs below.
    SUBAGENT 1 VALIDATED 2026 ARTICLES:
    {result_tool_subagent_1_validated}
    SUBAGENT 2 VALIDATED 2026 ARTICLES:
    {result_tool_subagent_2_validated}
    SUBAGENT 3 VALIDATED 2026 ARTICLES:
    {result_tool_subagent_3_validated}
    """,
    description="Reads validated records and presents the final list with a brief introduction.",
)
# ====================================================================
# Root Agent Definition
# ====================================================================
def before_root_agent(callback_context: CallbackContext) -> None:
    """Captures root query in state and logs initial state."""
    if callback_context.user_content and callback_context.user_content.parts:
        callback_context.state["query_root_agent"] = callback_context.user_content.parts[0].text
    print_state_snapshot("\n\nbefore_root_agent", callback_context.state)
    return None

root_agent = SequentialAgent(
    name="root_agent",
    sub_agents=[parallel_research_agent, validator_agent, merger_agent],
    description="Coordinates parallel research, validation, and synthesis.",
    before_agent_callback=before_root_agent,
)
# ====================================================================
# Session & Runner Orchestration
# ====================================================================
session_service = InMemorySessionService()
APP_NAME = "test_workflow_session_state_app"
DEFAULT_USER_ID = "user_1"
runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)

async def run_orchestrated_research(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes the complete orchestrated research workflow and returns final state.
    """
    user_id = DEFAULT_USER_ID
    sid = session_id or f"session_{uuid.uuid4().hex[:8]}"
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=sid,
    )

    # Initial state setup
    session.state["query_user"] = query
    print_state_snapshot("\n\ninitial_session_created", session.state)

    content = types.Content(role="user", parts=[types.Part(text=query)])
    final_response = "No response generated."

    async for event in runner.run_async(user_id=user_id, session_id=sid, new_message=content):
        author = getattr(event, "author", "System")
        if getattr(event, "is_final_response", lambda: False)():
            if author in ["merger_agent", "root_agent"]:
                if event.content and event.content.parts:
                    final_response = event.content.parts[0].text

    # Retrieve updated session state
    updated_session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=sid,
    )
    final_state = updated_session.state if updated_session else {}
    print_state_snapshot("\n\nfinal_workflow_completed", final_state)

    return {
        "query_user": final_state.get("query_user"),
        "query_root_agent": final_state.get("query_root_agent"),
        "query_subagent_1": final_state.get("query_subagent_1"),
        "query_subagent_2": final_state.get("query_subagent_2"),
        "query_subagent_3": final_state.get("query_subagent_3"),
        "result_tool_subagent_1": final_state.get("result_tool_subagent_1", []),
        "result_tool_subagent_2": final_state.get("result_tool_subagent_2", []),
        "result_tool_subagent_3": final_state.get("result_tool_subagent_3", []),
        "result_tool_subagent_1_validated": final_state.get("result_tool_subagent_1_validated", []),
        "result_tool_subagent_2_validated": final_state.get("result_tool_subagent_2_validated", []),
        "result_tool_subagent_3_validated": final_state.get("result_tool_subagent_3_validated", []),
        "final_response": final_response,
    }

# ====================================================================
# Main Execution Entrypoint
# ====================================================================
async def main():
    test_query = (
    "Investigate recent AI chip architectures and open-weights model "
    "breakthroughs, focusing on performance scaling and enterprise adoption."
    )
    print("\n" + "#" * 80)
    print(f"STARTING ORCHESTRATED TEST RUN")
    print(f"USER QUERY: {test_query}")
    print("#" * 80 + "\n")

    result = await run_orchestrated_research(test_query)

if __name__ == "__main__":
    asyncio.run(main())