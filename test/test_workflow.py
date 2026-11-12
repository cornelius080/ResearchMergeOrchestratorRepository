"""
test/test_workflow.py
====================================================================
Standalone test script for /api/research.
Uses requests only; measures only the POST call; writes results to test/workflow_result.md.
Output file path (relative): test/workflow_result.md
====================================================================
"""

import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config import SEARCH_MAX_RESULTS, SEARCH_TIMEOUT, MODEL_LCW

URL = "http://localhost:8000/api/research/debug"
PAYLOAD = {"message": "Analyze the latest and most relevant developments from NVIDIA in AI, including new chips and architectures, roadmap, partnerships, investments, and impact on the AI ecosystem."}
# PAYLOAD = {"message": "Analyze the latest developments in open-weights AI models. Compare the most relevant models, their capabilities, licenses, benchmarks, costs, and key use cases. Highlight emerging trends and recent releases."}
# PAYLOAD = {"message": "Analyze the latest developments in AI agents, including new frameworks and models, agentic capabilities, tool use, interoperability, enterprise use cases, and key players. Highlight the most relevant developments and emerging trends."}
TIMEOUT = 180
MD_PATH = str(Path(__file__).resolve().parent / "workflow_result.md")


def main():
    print("=" * 50)
    print("TESTING /api/research/debug endpoint")
    print("=" * 50)
    print(f"URL: {URL}")
    print(f"Payload: {PAYLOAD}")
    print(f"Model_LCW: {MODEL_LCW}")
    print()

    try:
        start = time.time()
        resp = requests.post(URL, json=PAYLOAD, timeout=TIMEOUT)
        elapsed = time.time() - start

        print(
            f"Status: {resp.status_code} | Elapsed Time for the complete workflow: {elapsed:.2f}s | "
            f"Max_Results: {SEARCH_MAX_RESULTS} | Timeout: {SEARCH_TIMEOUT} | Results File: {MD_PATH}\n\n"
        )
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    try:
        data = resp.json()
    except Exception as e:
        print(f"Invalid JSON response: {e}")
        print("Raw text:")
        print(resp.text[:2000])
        sys.exit(1)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# Workflow Result\n\n")
        f.write(f"**Elapsed time:** {elapsed:.2f}s\n\n")
        f.write("## Queries\n\n")
        for k in ["query_user", "query_root_agent", "query_subagent_1", "query_subagent_2", "query_subagent_3"]:
            f.write(f"- **{k}**: {data.get(k)}\n")
        f.write("\n## Final Response\n\n")
        f.write(str(data.get("final_response") or "N/A") + "\n")
        f.write("\n## Tool Results\n\n")
        for k in ["result_tool_subagent_1", "result_tool_subagent_2", "result_tool_subagent_3"]:
            f.write(f"### {k}\n\n")
            v = data.get(k)
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        f.write(f"- **title**: {item.get('title')}\n")
                        f.write(f"  **link**: {item.get('link')}\n")
                        f.write(f"  **pub_date**: {item.get('pub_date')}\n")
                        content = item.get("content", "")
                        f.write(f"  **content**: {content[:200]}{'...' if len(content) > 200 else ''}\n\n")
                    else:
                        f.write(f"- {item}\n")
            else:
                f.write(str(v or "N/A") + "\n")
        f.write("\n## Validated Results\n\n")
        for k in ["result_tool_subagent_1_validated", "result_tool_subagent_2_validated", "result_tool_subagent_3_validated"]:
            f.write(f"### {k}\n\n")
            v = data.get(k)
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        f.write(f"- **title**: {item.get('title')}\n")
                        f.write(f"  **link**: {item.get('link')}\n")
                        f.write(f"  **pub_date**: {item.get('pub_date')}\n")
                        content = item.get("content", "")
                        f.write(f"  **content**: {content[:200]}{'...' if len(content) > 200 else ''}\n\n")
                    else:
                        f.write(f"- {item}\n")
            else:
                f.write(str(v or "N/A") + "\n")


if __name__ == "__main__":
    main()
