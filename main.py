"""
main.py
====================================================================
Entry point for the FastAPI application.
Run it using: uvicorn main:app --reload
====================================================================
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Any, Dict
from workflows.orchestrator import run_orchestrated_research

# ====================================================================
# Application Setup
# ====================================================================
app = FastAPI(
    title="Research Merge Orchestrator",
    description="Multi-agent AI orchestrator coordinating parallel web research and synthesis.",
    version="1.0.0",
)

# CORS Middleware: Essential if running the frontend on a separate dev
# server (e.g., Live Server/Vite) or handling external API calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict this to your actual domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================================================================
# Models
# ====================================================================
class MessagePayload(BaseModel):
    """Payload for research requests."""
    message: str

# ====================================================================
# API Routes
# ====================================================================
@app.get("/api/status")
async def get_status() -> Dict[str, str]:
    """
    Health check endpoint useful for Docker or Load Balancers.

    Returns:
        Dict[str, str]: Status information.
    """
    return {"status": "ok", "service": "running"}

@app.post("/api/research")
async def process_research(payload: MessagePayload) -> str:
    """
    Endpoint for the final user. Delegates research to the orchestrator
    and returns ONLY the final synthesized report.

    Args:
        payload (MessagePayload): The user's research query.

    Returns:
        str: The final synthesized research report.
    """
    result = await run_orchestrated_research(payload.message)
    return result.get("final_response", "No final response was generated.")

@app.post("/api/research/debug")
async def process_research_debug(payload: MessagePayload) -> Dict[str, Any]:
    """
    Debug endpoint for developers. Delegates research to the orchestrator
    and returns the FULL result set, including intermediate steps and tool outputs.

    Args:
        payload (MessagePayload): The user's research query.

    Returns:
        Dict[str, Any]: The comprehensive result set from the orchestrator.
    """
    return await run_orchestrated_research(payload.message)

# ====================================================================
# Static Files (Frontend)
# ====================================================================
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")