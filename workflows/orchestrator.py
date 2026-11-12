"""
workflows/orchestrator.py
====================================================================
Multi-agent workflow orchestrator for research and synthesis.
Coordinates parallel web search sub-agents, validation, and synthesis merger.
====================================================================
"""

import uuid
from typing import Optional, Dict, Any

from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

from agents.sub_agents import subagent_1, subagent_2, subagent_3
from agents.validator_agent import validator_agent
from agents.synthesis_agent import merger_agent
from config.config import MODEL_LCW, APP_NAME, DEFAULT_USER_ID
from langfuse import observe, get_client, propagate_attributes


def before_root_agent(callback_context: CallbackContext) -> None:
    """
    Tracks the root agent input query in session state.

    Args:
        callback_context (CallbackContext): The ADK callback context.
    """
    if callback_context.user_content and callback_context.user_content.parts:
        callback_context.state["query_root_agent"] = callback_context.user_content.parts[0].text
    return None


parallel_research_agent = ParallelAgent(
    name="ParallelWebResearchAgent",
    sub_agents=[subagent_1, subagent_2, subagent_3],
    description="Runs multiple research agents in parallel to gather information.",
)

# Root agent coordinating parallel search, validation, and final synthesis in sequence
root_agent = SequentialAgent(
    name="root_agent",
    sub_agents=[parallel_research_agent, validator_agent, merger_agent],
    description="Coordinates parallel research, validates results, and synthesizes the output.",
    before_agent_callback=before_root_agent,
)

session_service = InMemorySessionService()

runner = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    session_service=session_service,
)


def clean_report_output(text: str) -> str:
    """
    Cleans up common LLM artifacts and markdown formatting from synthesis reports.

    Args:
        text (str): The raw synthesis report text.

    Returns:
        str: The cleaned report text.
    """
    if not text:
        return ""

    marker = "1. Main Body"
    idx = text.find(marker)
    if idx != -1:
        start_idx = text.rfind("#", 0, idx)
        if start_idx != -1:
            return text[start_idx:].strip()

    return text.strip()


@observe(name="Research_Orchestrator_Workflow")
async def run_orchestrated_research(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Entry point to run the parallel research, validation, and synthesis workflow.

    Args:
        query (str): The user's research query.
        session_id (Optional[str]): Existing session ID to maintain state.

    Returns:
        Dict[str, Any]: A comprehensive result set containing queries,
                        intermediate research summaries, validated records, and the final report.
    """
    user_id = DEFAULT_USER_ID
    sid = session_id or f"session_{uuid.uuid4().hex[:8]}"

    # Propagate session-level telemetry context across all nested observations
    with propagate_attributes(
        session_id=sid,
        user_id=user_id,
        tags=["multi-agent", "adk-orchestration", "web-research", "gemini-native", "validated"],
        metadata={
            "app_name": APP_NAME,
            "session_id": sid,
            "user_id": user_id,
            "model_lcw": MODEL_LCW,
        }
    ):
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=sid,
        )
        content = types.Content(role='user', parts=[types.Part(text=query)])
        final_response = "The SynthesisAgent did not produce a response (possible internal error or hanging)."

        subagent_1_q = None
        subagent_2_q = None
        subagent_3_q = None

        try:
            async for event in runner.run_async(user_id=user_id, session_id=sid, new_message=content):
                author = getattr(event, 'author', 'System')

                # Capture tool query argument for telemetry/response payload
                for fc in getattr(event, 'get_function_calls', lambda: [])():
                    if getattr(fc, 'name', '') == 'duckduckgo_search':
                        call_args = getattr(fc, 'args', {}) or {}
                        call_q = call_args.get('query')
                        if author == 'subagent_1' and not subagent_1_q:
                            subagent_1_q = call_q
                        elif author == 'subagent_2' and not subagent_2_q:
                            subagent_2_q = call_q
                        elif author == 'subagent_3' and not subagent_3_q:
                            subagent_3_q = call_q

                if getattr(event, 'is_final_response', lambda: False)():
                    if author in ["SynthesisAgent", "root_agent"]:
                        if event.content and event.content.parts:
                            final_response = clean_report_output(event.content.parts[0].text)
                        elif hasattr(event, 'actions') and getattr(event.actions, 'escalate', False):
                            final_response = f"Error in SynthesisAgent: {getattr(event, 'error_message', 'No message')}"

            # Log the final synthesis report generation record in Langfuse
            langfuse = get_client()
            with langfuse.start_as_current_observation(
                as_type="generation",
                name="Synthesis_Report_Generation",
                model=MODEL_LCW,
                input=query,
            ) as generation:
                if final_response.startswith("Error") or final_response.startswith("[GRAPH EXECUTION ERROR]"):
                    generation.update(output=final_response, level="ERROR", status_message=final_response)
                else:
                    generation.update(output=final_response)

        except Exception as e:
            final_response = f"[GRAPH EXECUTION ERROR]: {e}"
            langfuse = get_client()
            with langfuse.start_as_current_observation(
                as_type="generation",
                name="Synthesis_Report_Generation",
                input=query,
            ) as generation:
                generation.update(output=final_response, level="ERROR", status_message=str(e))
        finally:
            # Commit pending telemetry events before returning response
            get_client().flush()

        # Retrieve updated session state where callbacks and output_keys stored data
        updated_session = await session_service.get_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=sid,
        )
        state = updated_session.state if updated_session else {}

        return {
            # 1. User query
            "query_user": query,

            # 2. Workflow root query
            "query_root_agent": state.get("query_root_agent", query),

            # 3, 4, 5. Queries sent to duckduckgo_search
            "query_subagent_1": state.get("query_subagent_1") or subagent_1_q,
            "query_subagent_2": state.get("query_subagent_2") or subagent_2_q,
            "query_subagent_3": state.get("query_subagent_3") or subagent_3_q,

            # 6, 7, 8. Raw subagent tool search results
            "result_tool_subagent_1": state.get("result_tool_subagent_1"),
            "result_tool_subagent_2": state.get("result_tool_subagent_2"),
            "result_tool_subagent_3": state.get("result_tool_subagent_3"),

            # 9, 10, 11. Validated subagent tool search results
            "result_tool_subagent_1_validated": state.get("result_tool_subagent_1_validated", []),
            "result_tool_subagent_2_validated": state.get("result_tool_subagent_2_validated", []),
            "result_tool_subagent_3_validated": state.get("result_tool_subagent_3_validated", []),

            # 12. Final synthesized response
            "final_response": final_response,
        }