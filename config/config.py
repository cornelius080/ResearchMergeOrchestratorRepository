"""
config/config.py
====================================================================
Centralized configuration management for Research Merge Orchestrator.
Supports both .env file loading and system environment variables.
Native Google GenAI / Google ADK configuration (no LiteLLM/Ollama).
====================================================================
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the configuration module
BASE_DIR = Path(__file__).resolve().parent

# Check for .env in current folder (config/) or in project root
ENV_FILE = BASE_DIR / ".env"
if not ENV_FILE.exists():
    ENV_FILE = BASE_DIR.parent / ".env"

load_dotenv(dotenv_path=ENV_FILE)

# ====================================================================
# API Keys & Credentials (Unified Google / Gemini Resolution)
# ====================================================================
# Resolves the API key supporting both GEMINI_API_KEY and GOOGLE_API_KEY
GOOGLE_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or ""
)

if GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
else:
    logging.warning("No Google/Gemini API key found in environment or .env file.")

# ====================================================================
# Model Configuration (Google GenAI Native Identifiers)
# ====================================================================
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-3.5-flash-lite")
MODEL_LCW_NAME = os.getenv("MODEL_LCW_NAME", "gemini-3.6-flash")


def get_model(model_name: str | None = None) -> str:
    """
    Returns the native Google GenAI model string identifier for Google ADK agents.

    Args:
        model_name (str | None): Optional specific model identifier.

    Returns:
        str: Model identifier string recognized natively by Google ADK.
    """
    return model_name or MODEL_NAME


# Dedicated model string identifiers
MODEL = get_model(MODEL_NAME)
MODEL_LCW = get_model(MODEL_LCW_NAME)

# ====================================================================
# Application Context Settings
# ====================================================================
APP_NAME = os.getenv("APP_NAME", "research_merge_orchestrator_app")
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "user_1")

# Web Search Parameters
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "8"))
SEARCH_TIMEOUT = int(os.getenv("SEARCH_TIMEOUT", "8"))

# Target Domains for Sub-Agents
DOMAIN_1 = os.getenv("DOMAIN_1", "deeplearning.ai/the-batch")
DOMAIN_2 = os.getenv("DOMAIN_2", "techcrunch.com")
DOMAIN_3 = os.getenv("DOMAIN_3", "arstechnica.com/ai")

# ====================================================================
# Langfuse Telemetry Configuration
# ====================================================================
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")