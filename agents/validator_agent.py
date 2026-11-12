"""
agents/validator_agent.py
====================================================================
Specialized Validation Agent for multi-agent web research results.
Validates candidate articles using strict short-circuit logic:
1. Domain check (evaluates ONLY 'link')
2. Date check (evaluates ONLY 'pub_date' <= 4 months)
3. Relevance check (evaluates ONLY 'title' and 'link' vs user query)

Extracts and validates indices into a Pydantic model and purges
ephemeral candidate strings from session state upon completion.
====================================================================
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types
from config.config import MODEL, DOMAIN_1, DOMAIN_2, DOMAIN_3

logger = logging.getLogger(__name__)


# ====================================================================
# Pydantic Structured Output Schema (Domain-Agnostic)
# ====================================================================
class ValidationOutput(BaseModel):
    """
    Type-safe validation schema containing 0-based article indices
    for each sub-agent, independent of specific domain names.
    """
    agent_1_indices: List[int] = Field(
        default_factory=list,
        description=f"0-based integer indices of articles passing all 3 checks for {DOMAIN_1}."
    )
    agent_2_indices: List[int] = Field(
        default_factory=list,
        description=f"0-based integer indices of articles passing all 3 checks for {DOMAIN_2}."
    )
    agent_3_indices: List[int] = Field(
        default_factory=list,
        description=f"0-based integer indices of articles passing all 3 checks for {DOMAIN_3}."
    )


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


def calculate_cutoff_date(now: datetime, months: int = 4) -> datetime:
    """Computes a UTC date exactly N months prior to reference datetime."""
    year = now.year
    month = now.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(now.day, 28)
    return now.replace(year=year, month=month, day=day)


def clean_and_parse_json(raw_text: str) -> Dict[str, Any]:
    """Safely extracts JSON payload from plain text or markdown blocks."""
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
    except Exception as err:
        logger.warning("[validator_agent] JSON parsing failed: %s", err)
        return {}


def extract_indices_from_payload(data: Dict[str, Any]) -> ValidationOutput:
    """
    Extracts validated indices from either flat keys or nested dictionary structures,
    validating the final output into a typed ValidationOutput instance.
    """
    extracted: Dict[str, List[int]] = {
        "agent_1_indices": [],
        "agent_2_indices": [],
        "agent_3_indices": [],
    }

    # Inspect if indices are nested under a parent key like 'validated_indices'
    source = data
    for parent_key in ["validated_indices", "validation_results", "results"]:
        if parent_key in data and isinstance(data[parent_key], dict):
            source = data[parent_key]
            break

    # Flexible matching across agent index naming conventions
    mappings = [
        ("agent_1_indices", ["agent_1", "agent1", "subagent_1", "subagent1"]),
        ("agent_2_indices", ["agent_2", "agent2", "subagent_2", "subagent2"]),
        ("agent_3_indices", ["agent_3", "agent3", "subagent_3", "subagent3"]),
    ]

    for target_key, aliases in mappings:
        for k, v in source.items():
            normalized_key = k.lower().replace("_", "").replace("-", "")
            if any(alias in normalized_key for alias in aliases):
                if isinstance(v, list):
                    extracted[target_key] = [
                        int(i) for i in v if isinstance(i, (int, str)) and str(i).isdigit()
                    ]
                break

    return ValidationOutput.model_validate(extracted)


def before_validator_agent(callback_context: CallbackContext) -> None:
    """
    Prepares dynamic reference dates and standardized candidate records in state.
    Omits the heavy 'content' key to preserve low latency.
    """
    now = datetime.now(timezone.utc)
    cutoff = calculate_cutoff_date(now, months=4)

    callback_context.state["current_date"] = now.strftime("%Y-%m-%d")
    callback_context.state["cutoff_date"] = cutoff.strftime("%Y-%m-%d")

    raw_1 = callback_context.state.get("result_tool_subagent_1") or []
    raw_2 = callback_context.state.get("result_tool_subagent_2") or []
    raw_3 = callback_context.state.get("result_tool_subagent_3") or []

    def _format_records(items: List[Dict[str, Any]]) -> str:
        if not items:
            return "No candidate articles available."
        lines = []
        for idx, item in enumerate(items):
            lines.append(
                f"[Index: {idx}]\n"
                f"- Title: {item.get('title', 'No title')}\n"
                f"- Link: {item.get('link', '')}\n"
                f"- Publication Date: {item.get('pub_date', 'Unknown')}\n"
            )
        return "\n".join(lines)

    callback_context.state["candidate_records_subagent_1"] = _format_records(raw_1)
    callback_context.state["candidate_records_subagent_2"] = _format_records(raw_2)
    callback_context.state["candidate_records_subagent_3"] = _format_records(raw_3)
    return None


def after_validator_agent(callback_context: CallbackContext) -> None:
    """
    Post-execution callback: parses agent response into ValidationOutput,
    samples original full records, and populates the validated state keys.
    """
    raw_output = callback_context.state.get("validator_output", "")
    parsed_json = clean_and_parse_json(raw_output)
    validated_output = extract_indices_from_payload(parsed_json)

    # Retrieve original raw tool records containing the full untouched 'content'
    raw_1 = callback_context.state.get("result_tool_subagent_1") or []
    raw_2 = callback_context.state.get("result_tool_subagent_2") or []
    raw_3 = callback_context.state.get("result_tool_subagent_3") or []

    # Sample original records directly using the validated integer lists
    valid_1 = [raw_1[i] for i in validated_output.agent_1_indices if 0 <= i < len(raw_1)]
    valid_2 = [raw_2[i] for i in validated_output.agent_2_indices if 0 <= i < len(raw_2)]
    valid_3 = [raw_3[i] for i in validated_output.agent_3_indices if 0 <= i < len(raw_3)]

    # Store validated results in session state
    callback_context.state["result_tool_subagent_1_validated"] = valid_1
    callback_context.state["result_tool_subagent_2_validated"] = valid_2
    callback_context.state["result_tool_subagent_3_validated"] = valid_3

    # ====================================================================
    # Safe Destruction: Purge temporary data from state
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
        #callback_context.state[key] = None
        delete_state_key(callback_context.state, key)

    logger.info(
        "[validator_agent] Validation complete: %s (%d/%d), %s (%d/%d), %s (%d/%d)",
        DOMAIN_1, len(valid_1), len(raw_1),
        DOMAIN_2, len(valid_2), len(raw_2),
        DOMAIN_3, len(valid_3), len(raw_3)
    )
    return None


# ====================================================================
# Agent Definition
# ====================================================================
validator_agent = Agent(
    name="validator_agent",
    model=MODEL,
    generate_content_config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level="minimal",
            include_thoughts=False,
        ),
    ),
    output_key="validator_output",
    before_agent_callback=before_validator_agent,
    after_agent_callback=after_validator_agent,
    instruction=f"""
You are a meticulous Research Validation Assistant responsible for verifying and filtering candidate web articles retrieved by three search sub-agents.

### Context Inputs:
- User Query: "{{query_root_agent}}"
- Reference Today's Date: "{{current_date}}"
- Cutoff Date (Strict Threshold): "{{cutoff_date}}"

### Candidate Metadata Sets:
Article content has been omitted to ensure ultra-fast execution; evaluate ONLY the provided metadata fields ("Title", "Link", "Publication Date").

* CANDIDATE RECORDS AGENT 1 (Designated Domain: '{DOMAIN_1}'):
{{candidate_records_subagent_1}}

* CANDIDATE RECORDS AGENT 2 (Designated Domain: '{DOMAIN_2}'):
{{candidate_records_subagent_2}}

* CANDIDATE RECORDS AGENT 3 (Designated Domain: '{DOMAIN_3}'):
{{candidate_records_subagent_3}}

---

### MANDATORY SHORT-CIRCUIT VALIDATION PIPELINE
For EACH candidate article, you MUST execute the following three verification checks in this EXACT sequential order.
CRITICAL SHORT-CIRCUIT RULE: As soon as an article fails ANY verification check, it is IMMEDIATELY DISCARDED. You MUST NOT proceed to subsequent checks for that candidate.

#### CHECK 1: Domain Validation (Evaluates ONLY the "Link" key)
- Check whether the candidate's "Link" starts with or strictly belongs to the section's designated target domain:
  - Agent 1 candidates MUST match: '{DOMAIN_1}'
  - Agent 2 candidates MUST match: '{DOMAIN_2}'
  - Agent 3 candidates MUST match: '{DOMAIN_3}'
- If the "Link" is missing, empty, or points to an external/unauthorized domain:
  -> IMMEDIATELY DISCARD the article. Do NOT evaluate Check 2 or Check 3.

#### CHECK 2: Publication Date Validation (Evaluates ONLY the "Publication Date" key)
- For candidates that PASSED Check 1:
- Check whether the article was published within the last 4 months (on or after {{cutoff_date}}).
- If "Publication Date" is "Unknown", missing, unparseable, or older than {{cutoff_date}}:
  -> IMMEDIATELY DISCARD the article. Do NOT evaluate Check 3.

#### CHECK 3: Topic & Article Relevance Validation (Evaluates ONLY "Title" and "Link" against User Query)
- For candidates that PASSED Check 1 AND Check 2:
- Determine if the candidate represents an actual specific news article (NOT a generic category hub, tag index, or section landing page such as 'techcrunch.com/category/...' or 'arstechnica.com/ai').
- Evaluate whether the article's "Title" and "Link" are directly relevant to the User Query: "{{query_root_agent}}".
- If the candidate is a category/index page, or is irrelevant/off-topic:
  -> DISCARD the article.
- If it passes Check 3:
  -> The article is VALID. Record its integer index.

---

### OUTPUT FORMAT
Output ONLY a JSON block in the following format:
```json
{{
  "agent_1_indices": [0, 1, 2],
  "agent_2_indices": [0],
  "agent_3_indices": [1, 2]
}}
Do not include any conversational preamble or text outside the JSON block.
""",
description="Validates candidate research articles using sequential domain, date, and relevance checks.",
)